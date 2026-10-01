#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gunluk_is.py — günlük otomatik koşu (launchd her gün 09:00)

Sıra:
  1. Resmî Gazete taraması (ikinci sinyal — hızlı, önce koşar)
  2. mevzuat.gov.tr güncellik denetimi (yavaş, ~3 dk)
  3. Günlük özet sayfası (yayin.py) → mevzuat-ozet.vercel.app → canlıda
     doğrulama → Bark bildirimi (dokununca sayfa açılır)

KULLANICI KARARI (26.09.2026): bildirim HER GÜN gider — değişiklik yoksa
"değişiklik yok" der. (19.09.2026'daki "yalnız kritik+önemli" kuralının yerini
aldı: sessizlik "sistem çalışmıyor" ile karıştırılıyordu.) Gün içindeki acil
bildirimler ayrı iştir: acil_is.py (com.mevzuat.acil).

Çıkış kodu: 0 sorunsuz · 1 olay var · 2 hata (yayın/bildirim dahil) · 3 devre kesici
"""
import json
import os
import subprocess
import sys
from datetime import datetime

import bildirim
import cekirdek as c
import motor

KAYIT_DIR = os.path.join(motor.KOK, "kayit")
RG_DURUM = os.path.join(KAYIT_DIR, "rg-gorulen.json")


def _yaz(s):
    print(s, flush=True)


def rg_adimi(gun=3):
    """RG taraması. Aynı kaydı her gün yeniden bildirmemek için görülenler
    `kayit/rg-gorulen.json`'da tutulur."""
    import rg as rgm
    kaynak = c.yukle(motor.KAYNAK)
    try:
        bulgular, hatalar, tarandi = rgm.tara(gun, izlenen=kaynak.get("mevzuat", []))
    except Exception as e:
        _yaz(f"  RG taraması başarısız: {type(e).__name__}: {e}")
        return [], [f"RG: {e}"]

    gorulen = set(c.yukle(RG_DURUM, {"anahtarlar": []})["anahtarlar"])
    yeni = []
    for b in bulgular:
        anahtar = f"{b['tarih']}|{b['baslik'][:120]}"
        if anahtar not in gorulen:
            yeni.append(b)
            gorulen.add(anahtar)
    os.makedirs(KAYIT_DIR, exist_ok=True)
    c.kaydet(RG_DURUM, {"anahtarlar": sorted(gorulen)[-4000:],
                        "son_tarama": datetime.now().isoformat(timespec="seconds")})
    _yaz(f"  {tarandi} gün okundu · {len(bulgular)} ilgili · {len(yeni)} YENİ")
    for b in yeni:
        _yaz(f"    · {b['tarih']} {b['baslik'][:76]}")
        _yaz(f"      {' · '.join(b['sebep'])}")
    return yeni, [f"RG {g}: {h}" for g, h in hatalar]


def denetim_adimi():
    """mevzuat.py denetle — alt süreç olarak, çıktısı kayda alınır."""
    r = subprocess.run([sys.executable, os.path.join(motor.KOK, "mevzuat.py"), "denetle"],
                       capture_output=True, text=True, cwd=motor.KOK, timeout=2400)
    import re
    ham = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout + r.stderr)
    for s in ham.splitlines():
        _yaz("  " + s)
    return r.returncode, ham


def main():
    os.makedirs(KAYIT_DIR, exist_ok=True)
    basladi = datetime.now()
    _yaz(f"\n{'='*70}\nGÜNLÜK MEVZUAT İŞİ · {basladi:%d.%m.%Y %H:%M}\n{'='*70}")
    import yayin
    # Acil iş (acil_is.py) aynı dosyalara yazar: kilit alınana kadar beklenir.
    with yayin.is_kilidi(bekle=True) as kilit:
        uyarilar = []
        if kilit is None:
            uyarilar.append("İş kilidi 30 dk'da açılmadı — acil iş takılmış olabilir")

        _yaz("\n[1/3] Resmî Gazete taraması")
        rg_yeni, rg_hata = rg_adimi(gun=3)
        if rg_hata:
            uyarilar.append(f"Resmî Gazete: {len(rg_hata)} gün okunamadı")

        _yaz("\n[2/3] mevzuat.gov.tr güncellik denetimi")
        onceki = len(c.yukle(motor.GUNLUK, {"olaylar": []})["olaylar"])
        kod, ham = denetim_adimi()
        yeni_olay = c.yukle(motor.GUNLUK, {"olaylar": []})["olaylar"][onceki:]
        if kod == 3:
            # Eskiden ayrı bildirim gidip iş burada bitiyordu; artık günlük özet
            # yine yayımlanır, uyarı en üstte durur (kullanıcı kararı 26.09.2026:
            # rutin bildirim her gün gider).
            uyarilar.append("DEVRE KESİCİ: külliyatın büyük bölümü aynı anda 'değişti' "
                            "göründü (muhtemelen pdftotext sürümü) — hiçbir dosya "
                            "güncellenmedi, inceleme gerekiyor")
        import re
        m = re.search(r"(\d+) ulaşılamadı", ham)
        if m and int(m.group(1)):
            uyarilar.append(f"{m.group(1)} belgeye ulaşılamadı — depodaki nüshaları bayat olabilir")

        # Günlük özet: sayfa üret → Vercel → canlıda doğrula → Bark (link ile).
        # Değişiklik olmasa da gider: "değişiklik yok" = "sistem çalıştı".
        _yaz("\n[3/3] Günlük özet sayfası ve bildirim")
        yayin_kod, rapor = yayin.gunluk(uyarilar=uyarilar)
        for s in rapor.splitlines():
            _yaz("  " + s)

    sure = (datetime.now() - basladi).total_seconds()
    _yaz(f"\nbitti · {sure:.0f} sn · {len(yeni_olay)} mevzuat olayı · "
         f"{len(rg_yeni)} yeni RG kaydı" + (f" · {len(uyarilar)} uyarı" if uyarilar else ""))
    if kod == 3:
        return 3
    if yayin_kod:
        return 2
    return 1 if (yeni_olay or rg_yeni) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"GÜNLÜK İŞ ÇÖKTÜ: {type(e).__name__}: {e}", file=sys.stderr)
        try:
            import bildirim as b
            b.gonder("❌ Mevzuat takibi çöktü", f"{type(e).__name__}: {e}")
        except Exception:
            pass
        sys.exit(2)
