#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bildirim.py — Bark köprüsü

KULLANICI KARARI (19.09.2026): bildirim KRİTİK + ÖNEMLİ olaylarda gider.
`bilgi` şiddetindeki olaylar (metin değişti ama madde envanteri aynı —
dizgi/dipnot oynaması) yalnız arayüzde görünür, telefonu rahatsız etmez.

Cihaz anahtarı ~/.config/bark/bark.env içindedir; bu dosya onu OKUMAZ,
script kendisi okur. Anahtar log'a, mesaja ya da koda yazılmaz.

DİKKAT: bark.sh'in {"code":200} dönmesi "APNs kabul etti" demektir,
"telefonda göründü" DEMEZ. Bu yüzden ham yanıt olduğu gibi raporlanır.
"""
import os
import subprocess

BARK = os.path.expanduser("~/Projects/_global-scripts/bark/bark.sh")

SIDDET_SIRASI = {"kritik": 3, "onemli": 2, "bilgi": 1}
ESIK = "onemli"          # bu ve üstü bildirilir


def gonderilebilir(olaylar):
    return [o for o in olaylar
            if SIDDET_SIRASI.get(o.get("siddet"), 0) >= SIDDET_SIRASI[ESIK]]


def ozetle(olaylar):
    """-> (baslik, mesaj) · olay yoksa (None, None)"""
    ol = gonderilebilir(olaylar)
    if not ol:
        return None, None
    kritik = [o for o in ol if o.get("siddet") == "kritik"]
    belge = sorted({o.get("ad", o.get("slug", "")) for o in ol})

    if kritik:
        baslik = f"⚖️ Mevzuat: {len(kritik)} kritik değişiklik"
    else:
        baslik = f"⚖️ Mevzuat: {len(ol)} değişiklik"

    satir = []
    for o in (kritik or ol)[:4]:
        ad = o.get("ad", o.get("slug", ""))
        satir.append(f"• {ad[:34]} — {o.get('ozet', '')[:72]}")
    if len(ol) > len(satir):
        satir.append(f"… {len(ol) - len(satir)} olay daha")
    satir.append(f"({len(belge)} belge) http://127.0.0.1:3031/gunluk")
    return baslik, "\n".join(satir)


def rg_ozetle(bulgular):
    """Resmî Gazete sinyali için ayrı özet (Ö-1)."""
    if not bulgular:
        return None, None
    kritik = [b for b in bulgular if b.get("siddet") == "kritik"]
    baslik = (f"📰 Resmî Gazete: {len(kritik)} kritik kayıt" if kritik
              else f"📰 Resmî Gazete: {len(bulgular)} ilgili kayıt")
    satir = []
    for b in (kritik or bulgular)[:4]:
        satir.append(f"• {b['baslik'][:80]}")
        satir.append(f"  ({' · '.join(b.get('sebep', []))})")
    if len(bulgular) > 4:
        satir.append(f"… {len(bulgular) - 4} kayıt daha")
    return baslik, "\n".join(satir)


def gonder(baslik, mesaj, kritik=False, url=None, seviye=None, grup="mevzuat"):
    """-> (basarili_mi, ham_yanit)
    'gönderildi' demeden önce ham yanıt kontrol edilir.

    url: bildirime dokununca açılacak adres (26.09.2026'dan beri günlük özet ve
    acil bildirim yayın sayfasını taşır). seviye: "timeSensitive" acil içindir;
    --kritik DEĞİLDİR — o yalnız kullanıcı "beni uyandır" dediğinde."""
    if not baslik or not mesaj:
        return True, "(gönderilecek olay yok)"
    if not os.path.exists(BARK):
        return False, f"bark.sh bulunamadı: {BARK}"
    komut = [BARK, baslik, mesaj] + (["--kritik"] if kritik else [])
    if url:
        komut += ["--url", url]
    if seviye:
        komut += ["--seviye", seviye]
    if grup:
        komut += ["--grup", grup]
    try:
        r = subprocess.run(komut, capture_output=True, text=True, timeout=45)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    ham = (r.stdout + r.stderr).strip()
    return ('"code":200' in ham.replace(" ", "")), ham


if __name__ == "__main__":
    import sys
    import cekirdek as c
    import motor
    g = c.yukle(motor.GUNLUK, {"olaylar": []})
    yeni = [o for o in g["olaylar"] if not o.get("okundu")]
    b, m = ozetle(yeni)
    if not b:
        print("Bildirilecek olay yok.")
        sys.exit(0)
    print(f"BAŞLIK: {b}\nMESAJ:\n{m}\n")
    if "--gonder" in sys.argv:
        ok, ham = gonder(b, m, kritik=any(o.get("siddet") == "kritik" for o in yeni))
        print(("✅ " if ok else "❌ ") + "ham yanıt: " + ham)
        sys.exit(0 if ok else 1)
    print("(denemeydi — gerçekten göndermek için: --gonder)")
