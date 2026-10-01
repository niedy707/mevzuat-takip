#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
acil_is.py — ÇEKİRDEK belgelerin gün içi denetimi + ACİL bildirim

launchd com.mevzuat.acil · 07·10·13·16·19·22 (kullanıcı kararı 26.09.2026)
09:00'daki tam denetim ve günlük özet ayrı iştir: gunluk_is.py.

KAPSAM (kullanıcı kararı 26.09.2026):
  · ACİL LİSTESİNDEKİ belgeler gün içinde denetlenir; bunlarda KRİTİK ya da
    ÖNEMLİ her madde olayı ACİL'dir. Liste arayüzden seçilir (127.0.0.1:3031 →
    Mevzuat → 🚨 acil) ve acil-secim.json'da durur; dosya yoksa varsayılan
    kaynak.json'daki "cekirdek" sınıfıdır (19 belge).
  · Resmî Gazete: acil listesindeki bir belgeyi anan kayıt ve her "yürütmenin
    durdurulması" kaydı ACİL'dir.
  Geri kalan her şey ertesi sabahın günlük özetini bekler.

ACİL bulunursa: yayin.acil() → ayrı sayfa (mevzuat-ozet.vercel.app/acil/…)
→ canlıda doğrulama → Bark (timeSensitive, dokununca sayfa açılır).
Acil bulunmazsa bildirim GİTMEZ; koşu kayit/acil-nabiz.json'a yazılır ve
günlük özet sayfası "acil kontrol: son koşu …" diye gösterir — acil iş
sessizce durursa ertesi sabah görünür (ekosistem kuralı § 7).

    python3 acil_is.py            normal koşu
    python3 acil_is.py --deneme   zinciri sına: son kritik değişiklikle "🧪 DENEME"
                                  sayfası + bildirim; hiçbir kayda "bildirildi" yazılmaz

Çıkış: 0 acil yok (ya da günlük iş sürdüğü için atlandı) · 1 acil bildirildi · 2 hata
"""
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

import cekirdek as c
import degisiklik as dg
import motor
import yayin

ACIL_SIDDET = ("kritik", "onemli")
TAZE_GUN = 3          # ilk koşuda geçmiş olaylar "acil" diye yeniden bildirilmesin


def _yaz(s):
    print(s, flush=True)


ACIL_SECIM = os.path.join(motor.KOK, "acil-secim.json")


def cekirdek_sluglar(kaynak):
    return {m["slug"] for m in kaynak.get("mevzuat", []) if m.get("sinif") == "cekirdek"}


def acil_sluglar(kaynak):
    """Acil kapsamdaki belgeler. Kullanıcı arayüzden (127.0.0.1:3031 → Mevzuat →
    🚨 acil) seçer; seçim acil-secim.json'da durur. Dosya yoksa varsayılan
    kullanıcının 26.09.2026 kararıdır: çekirdek sınıfı. kaynak.json'da artık
    olmayan slug sessizce düşer (belge izlemeden çıkarılmış demektir)."""
    bilinen = {m["slug"] for m in kaynak.get("mevzuat", [])}
    secim = c.yukle(ACIL_SECIM, {})
    if "sluglar" in secim:
        return set(secim["sluglar"]) & bilinen
    return cekirdek_sluglar(kaynak)


def acil_secim_degistir(slug, acik, kaynak=None):
    """Bir belgeyi acil kapsama alır/çıkarır -> yeni küme. Bilinmeyen slug: ValueError."""
    kaynak = kaynak or c.yukle(motor.KAYNAK, {"mevzuat": []})
    if slug not in {m["slug"] for m in kaynak.get("mevzuat", [])}:
        raise ValueError(f"bilinmeyen belge: {slug}")
    kume = acil_sluglar(kaynak)
    (kume.add if acik else kume.discard)(slug)
    c.kaydet(ACIL_SECIM, {
        "_aciklama": "Acil bildirim kapsamındaki belgeler (acil_is.py okur). Arayüzden "
                     "değiştirilir: 127.0.0.1:3031 → Mevzuat → 🚨 acil. Dosya silinirse "
                     "varsayılan: kaynak.json'da sinif=cekirdek olanlar.",
        "guncelleme": datetime.now().isoformat(timespec="seconds"),
        "sluglar": sorted(kume)})
    return kume


def acil_mi(k, cekirdek):
    """Kullanıcı kararı (26.09.2026) — bkz. modül başı."""
    if k.get("aym"):
        return False
    if k["kaynak"] == "mevzuat":
        return k.get("slug") in cekirdek and k.get("siddet") in ACIL_SIDDET
    return k.get("slug") in cekirdek or "YÜRÜTMENİN DURDURULMASI" in k.get("ozet", "")


def islenmis_mi(k, durum_y):
    """Bu kalem daha önce acil bildirildi ya da bir günlük özette yayımlandı mı."""
    if k["kimlik"] in durum_y.get("acil_bildirilen", {}):
        return True
    yayinlanan = set(durum_y.get("gunluk_yayinlanan", []))
    return all(a in yayinlanan for a in k["anahtarlar"])


def taze_mi(k, simdi=None):
    simdi = simdi or datetime.now()
    try:
        return datetime.fromisoformat(k["zaman"]) >= simdi - timedelta(days=TAZE_GUN)
    except ValueError:
        return False


def nabiz_yaz(sonuc, **ek):
    n = c.yukle(yayin.ACIL_NABIZ, {"kosular": []})
    n["kosular"] = (n.get("kosular", []) + [dict(
        zaman=datetime.now().isoformat(timespec="seconds"), sonuc=sonuc, **ek)])[-60:]
    c.kaydet(yayin.ACIL_NABIZ, n)


def denetle(sluglar):
    """mevzuat.py denetle <çekirdek slug'lar> — alt süreç; çıktı kayda alınır."""
    r = subprocess.run([sys.executable, os.path.join(motor.KOK, "mevzuat.py"), "denetle",
                        *sorted(sluglar)], capture_output=True, text=True, cwd=motor.KOK,
                       timeout=1800)
    ham = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout + r.stderr)
    for s in ham.splitlines()[-8:]:
        _yaz("  " + s)
    return r.returncode, ham


def deneme():
    kalemler = [k for k in dg.tum_kalemler()
                if k["kaynak"] == "mevzuat" and k["siddet"] == "kritik"][:1]
    if not kalemler:
        _yaz("Deneme için kritik olay yok.")
        return 2
    kod, rapor = yayin.acil(kalemler, deneme=True)
    for s in rapor.splitlines():
        _yaz("  " + s)
    return kod


def main():
    basladi = datetime.now()
    _yaz(f"\n{'─'*70}\nACİL KONTROL · {basladi:%d.%m.%Y %H:%M}")
    with yayin.is_kilidi(bekle=False) as kilit:
        if kilit is None:
            _yaz("  günlük iş sürüyor — atlandı (günlük özet aynı kontrolü kapsar)")
            nabiz_yaz("atlandı: günlük iş sürüyordu")
            return 0
        if "--deneme" in sys.argv:
            return deneme()

        from gunluk_is import rg_adimi
        kaynak = c.yukle(motor.KAYNAK, {"mevzuat": []})
        cekirdek = acil_sluglar(kaynak)      # adı tarihsel: artık "seçili" küme

        _yaz("[1/3] Resmî Gazete (son 2 gün)")
        rg_yeni, rg_hata = rg_adimi(gun=2)
        _yaz(f"[2/3] acil kapsamdaki belgeler ({len(cekirdek)})")
        onceki = len(c.yukle(motor.GUNLUK, {"olaylar": []})["olaylar"])
        # Boş seçimde denetle ÇAĞRILMAZ: argümansız `denetle` 51 belgenin hepsini
        # denetler — kullanıcı bütün seçimleri kaldırınca 3 saatte bir tam denetim olurdu.
        kod, ham = denetle(cekirdek) if cekirdek else (0, "acil listesi boş — denetim atlandı")
        yeni_olay = len(c.yukle(motor.GUNLUK, {"olaylar": []})["olaylar"]) - onceki

        _yaz("[3/3] acil süzgeci")
        durum_y = c.yukle(yayin.YAYIN_DURUM, {})
        acil = [k for k in dg.tum_kalemler()
                if acil_mi(k, cekirdek) and taze_mi(k) and not islenmis_mi(k, durum_y)]
        hata = []
        if kod == 3:
            hata.append("devre kesici")
        m = re.search(r"(\d+) ulaşılamadı", ham)
        if m and int(m.group(1)):
            hata.append(f"{m.group(1)} belgeye ulaşılamadı")
        if rg_hata:
            hata.append(f"RG {len(rg_hata)} gün okunamadı")

        if not acil:
            _yaz("  acil kayıt yok — bildirim gönderilmedi")
            nabiz_yaz("temiz" + (f" ({'; '.join(hata)})" if hata else ""),
                      olay=yeni_olay, rg=len(rg_yeni))
            return 0

        _yaz(f"  {len(acil)} ACİL kayıt: " + "; ".join(k["kimlik"] for k in acil))
        ykod, rapor = yayin.acil(acil)
        for s in rapor.splitlines():
            _yaz("  " + s)
        nabiz_yaz(f"{len(acil)} acil bildirildi" if ykod == 0 else "acil bildirim HATASI",
                  olay=yeni_olay, rg=len(rg_yeni), acil=[k["kimlik"] for k in acil])
        return 1 if ykod == 0 else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as ex:
        print(f"ACİL KONTROL ÇÖKTÜ: {type(ex).__name__}: {ex}", file=sys.stderr)
        # Günde 6 koşu: kalıcı bir çökme telefonu boğmasın — günde BİR bildirim.
        try:
            n = c.yukle(yayin.ACIL_NABIZ, {"kosular": []})
            bugun = datetime.now().strftime("%Y-%m-%d")
            if n.get("cokme_bildirimi") != bugun:
                import bildirim
                bildirim.gonder("❌ Mevzuat acil kontrol çöktü", f"{type(ex).__name__}: {ex}")
                n["cokme_bildirimi"] = bugun
            n["kosular"] = (n.get("kosular", []) + [{
                "zaman": datetime.now().isoformat(timespec="seconds"),
                "sonuc": f"ÇÖKTÜ: {type(ex).__name__}"}])[-60:]
            c.kaydet(yayin.ACIL_NABIZ, n)
        except Exception:
            pass
        sys.exit(2)
