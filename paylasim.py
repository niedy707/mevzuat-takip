#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
paylasim.py — kardeş projelerin kullandığı SALT OKUNUR arayüz

Ekosistemde mevzuat metni **tek yerden** okunur: bu proje. `is-hukuku` ve
`5levent` kendi indirici/ayrıştırıcılarını taşımaz, buradan okur.

    import sys; sys.path.insert(0, "../mevzuat")
    import paylasim
    metin = paylasim.metin("634-kat-mulkiyeti")
    m17   = paylasim.madde("4857-is-kanunu", "17")

⚠️ Bu modül hiçbir şey İNDİRMEZ ve hiçbir dosya YAZMAZ. Güncelleme merkezin
kendi işidir (`python3 mevzuat.py denetle`, launchd 09:00). Böylece aynı anda
iki proje aynı sunucuya yüklenmez ve tek bir "son doğrulama" zamanı olur.

⚠️ Kardeş klasör bağımlılığı: bu dosya `~/Projects/mevzuat` içinde durur ve
çağıranlar onu `../mevzuat` göreli yoluyla bulur. Klasör tek başına taşınırsa
sessizce kırılır (ekosistemin bilinen tuzağı — bkz. kök `INFRASTRUCTURE.md`).
"""
import os

KOK = os.path.dirname(os.path.abspath(__file__))
MET_DIR = os.path.join(KOK, "metin")
DURUM_YOL = os.path.join(KOK, "durum.json")
KAYNAK_YOL = os.path.join(KOK, "kaynak.json")


class MevzuatYok(Exception):
    """İstenen mevzuat merkezde yok ya da hiç indirilmemiş."""


def _json(yol):
    import json
    with open(yol, encoding="utf-8") as f:
        return json.load(f)


def kayitlar():
    """Merkezin izlediği tüm mevzuat (kaynak.json kayıtları)."""
    return _json(KAYNAK_YOL)["mevzuat"]


def durum(slug=None):
    """Üretilen durum: imza, madde envanteri, son doğrulama…"""
    d = _json(DURUM_YOL)
    if slug is None:
        return d
    if slug not in d:
        raise MevzuatYok(
            f"'{slug}' merkezde indirilmemiş. Çalıştır: "
            f"cd {KOK} && python3 mevzuat.py indir {slug}")
    return d[slug]


def metin(slug):
    """Mevzuatın normalize edilmiş TAM METNİ (pdftotext -layout + NFKC)."""
    yol = os.path.join(MET_DIR, slug + ".txt")
    if not os.path.exists(yol):
        raise MevzuatYok(
            f"'{slug}' metni merkezde yok. Çalıştır: "
            f"cd {KOK} && python3 mevzuat.py indir {slug}")
    with open(yol, encoding="utf-8") as f:
        return f.read()


def madde(slug, no):
    """Tek bir maddenin LAFZI. -> {no, metin, durum, kunye, dipnot_blok}

    Madde sınırları merkezin envanterinden gelir; çağıran taraf kendi
    ayrıştırıcısını yazmaz."""
    import re
    import sys
    sys.path.insert(0, KOK)
    import analiz

    d = durum(slug)
    bilgi = (d.get("envanter") or {}).get(str(no))
    if not bilgi:
        raise MevzuatYok(f"'{slug}' içinde madde {no} yok.")
    ham = metin(slug)
    son = analiz.govde_siniri(ham)
    govde = ham[:son]
    isaret = list(analiz.MADDE.finditer(govde))
    for i, m in enumerate(isaret):
        if govde.count("\n", 0, m.start()) + 1 == bilgi["satir"]:
            bit = isaret[i + 1].start() if i + 1 < len(isaret) else son
            return {"slug": slug, "no": str(no),
                    "metin": re.sub(r"\n{3,}", "\n\n", govde[m.start():bit]).rstrip(),
                    "durum": bilgi["durum"],
                    "durum_adi": analiz.DURUM_ADI[bilgi["durum"]],
                    "kunye": bilgi.get("kunye", ""),
                    "dipnot_blok": bilgi.get("dipnot_blok", []),
                    "ad": d.get("ad"), "url": d.get("url"),
                    "sayfa_url": d.get("sayfa_url"),
                    "son_dogrulama": d.get("son_dogrulama")}
    raise MevzuatYok(f"'{slug}' envanteri metinle uyuşmuyor — merkezde `denetle` koş.")


def tazelik(slug):
    """-> (son_dogrulama_metni, kac_gun_once) · izleme bayatladı mı diye bakmak için."""
    from datetime import datetime
    d = durum(slug)
    s = d.get("son_dogrulama") or ""
    try:
        t = datetime.strptime(s.split()[0], "%d.%m.%Y")
        return s, (datetime.now() - t).days
    except Exception:
        return s, None


def merkez_yolu():
    return KOK


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 1:
        d = durum()
        print(f"merkez: {KOK}")
        print(f"izlenen: {len(kayitlar())} · indirilmiş: {len(d)}")
    elif len(sys.argv) == 2:
        s, gun = tazelik(sys.argv[1])
        print(f"{sys.argv[1]} · son doğrulama {s}"
              + (f" ({gun} gün önce)" if gun is not None else ""))
    else:
        print(madde(sys.argv[1], sys.argv[2])["metin"])
