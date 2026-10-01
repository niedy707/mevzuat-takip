#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analiz.py — Mevzuat metninden MADDE ENVANTERİ çıkarır ve iki envanteri
karşılaştırarak OLAY üretir.

Bu dosya projenin ayırt edici parçasıdır. Metin sha256'sı yalnız "bir şey
değişti" der; envanter karşılaştırması "NE değişti" der:

    madde_eklendi · madde_kaldirildi · madde_degisti
    madde_mulga   · madde_iptal      (Anayasa Mahkemesi)
    yurutme_durduruldu · yurutme_durdurma_kalkti   (Danıştay)

Ayrıştırıcı 19.09.2026'da 34 belgelik gerçek külliyatta ölçüldü:
3.690 madde çıkarıldı, yalnız 2 mükerrer anahtar kaldı (1219-tababet).
Ölçümde doğrulanan üç tuzak aşağıda `MADDE` ve `KUYRUK` yanında anlatıldı.
"""
import hashlib
import re
import unicodedata

# ── Kuyruk dizinleri ────────────────────────────────────────────────────────
# Kanun metinlerinin sonunda "hangi kanun hangi maddeyi değiştirdi" tabloları
# ve değiştiren kanunların KENDİ geçici maddelerinin tekrar basıldığı bölümler
# vardır. Gövdeye katılırsa envanter bozulur.
#
# TUZAK (ölçüldü): işaret "İŞLENEMEYEN HÜKÜM" değil — 193 sayılı Kanunda
# başlık "31/12/1960 TARİH VE 193 SAYILI KANUNA / İŞLENEMEYEN GEÇİCİ MADDELER:"
# biçimindedir. "HÜKÜM" arandığı sürece kesim geç yapılıyor ve "Geçici Madde 1"
# beş ayrı yerde görünüyordu. Bu yüzden yalnız "İŞLENEMEYEN" aranır.
KUYRUK = re.compile(
    r"(?im)^[^\n]{0,60}(?:"
    r"EK VE DEĞİŞİKLİK GETİREN MEVZUATIN"
    r"|İŞLENEMEYEN"
    r"|YÜRÜRLÜKTEN KALDIRILAN KANUN"
    r"|YÜRÜRLÜĞE GİRİŞ TARİHLERİNİ GÖSTERİR"
    r")[^\n]*$")

# ── Madde başlığı ───────────────────────────────────────────────────────────
# Biçimler: "Madde 17 –" · "MADDE 52-" · "Ek Madde 3 –" · "GEÇİCİ MADDE 1-"
#           "Mükerrer Madde 121 -" · "Madde 98/A-"
#
# İKİ TUZAK, İKİSİ DE ÖLÇÜLDÜ (19.09.2026):
#  1) "Mükerrer Madde 121", m.121'den AYRI bir maddedir (193'te 48 kez geçer).
#     Ön ek yakalanmazsa ikisi aynı anahtara düşer ve biri sessizce kaybolur.
#  2) "Madde 98/A" da m.98'den ayrıdır. Külliyatta 13/A, 17/A, 17/B, 18/A,
#     18/B, 22/A, 24/A, 183/A, Mükerrer 20/A–D … yaygın.
# Ayrıca ayraç ZORUNLUDUR: serbest bırakıldığında cümle içindeki
# "… 98 inci madde gereğince …" gibi ifadeler yanlış eşleşiyordu.
MADDE = re.compile(
    r"^[ \t]*(?:(?P<on>Ek|EK|Geçici|GEÇİCİ|Mükerrer|MÜKERRER)[ \t]+)?"
    r"(?:Madde|MADDE)[ \t]*(?P<no>\d+)"
    r"(?:[ \t]*/[ \t]*(?P<harf>[A-ZÇĞİÖŞÜ]))?"
    r"[ \t]*(?P<ayrac>[-–—/.:)]|$)", re.MULTILINE)

# ── Durum işaretleri ────────────────────────────────────────────────────────
# Danıştay yürütmeyi durdurma — yönetmeliklerde madde/fıkra/ibare düzeyinde
# parantez içinde belirtilir:
#   "(Danıştay Onuncu Dairesinin 31/12/2025 tarihli ve E.:2025/1600 sayılı
#     kararı ile yürütmesi durdurulan fıkra: …)"
YD = re.compile(r"yürütme(?:si|sinin|nin)?\s+durdurul", re.IGNORECASE)
# Anayasa Mahkemesi iptali — kanunlarda:
#   "(İptal ikinci cümle: Anayasa Mahkemesi'nin 25/12/2014 tarihli ve
#     E.: 2014/74, K.: 2014/201 sayılı Kararı ile.)"
IPTAL_AYM = re.compile(
    r"İptal[^)\n]{0,80}Anayasa\s+Mahkemesi|Anayasa\s+Mahkemesi[^)\n]{0,80}iptal",
    re.IGNORECASE)
MULGA = re.compile(r"\(\s*(?:Mülga|MÜLGA)\b")

# Dipnotlar: kanunda "(Değişik: 15/5/2008-5763/2 md.)",
#            yönetmelikte "(Ek:RG-29/8/2026-33355)" biçimindedir.
DIPNOT = re.compile(
    r"\((?:Değişik|Ek|Mülga|İptal|Yeniden düzenleme)[^)]{0,140}\)")

# ── Dipnot blokları (Ö-10) ─────────────────────────────────────────────────
# pdftotext -layout sayfa ALTINDAKİ dipnotları metin akışına serpiştirir.
# ÖLÇÜM (19.09.2026, 4857): 132 maddenin 22'sinin gövdesine bir dipnot bloğu
# düşüyor. Yani m.5'e dipnot eklenmesi, aynı sayfayı paylaşan m.80'in gövde
# hash'ini değiştirir → YANLIŞ "madde değişti" olayı. Bu yüzden dipnot blokları
# hash'ten ÖNCE ayrılır. Atılmaz: dipnotlar değişiklik tarihçesidir, ayrı
# alanda saklanır.
#
# Kanun biçimi:      tek başına "1" satırı + "2/7/2018 tarihli ve 700 sayılı …"
# Yönetmelik biçimi: tek başına "[1]" satırı + açıklama
DIPNOT_BLOK = re.compile(
    r"(?m)^[ \t]*(?:\[\d{1,3}\]|\d{1,3})[ \t]*\n"
    r"(?=[ \t]*(?:\d{1,2}/\d{1,2}/\d{4}\s+tarihli|Bu\s+(?:değişiklik|madde|fıkra|Yönetmelik)))"
    r"[^\n]*\n(?:[ \t]*(?![ \t]*(?:Ek |EK |Geçici |GEÇİCİ |Mükerrer |MÜKERRER )?"
    r"(?:Madde|MADDE)[ \t]*\d)[^\n]+\n)*")


def dipnot_ayir(govde):
    """Madde gövdesinden dipnot bloklarını ayırır.
    -> (temiz_govde, [dipnot metni, ...])"""
    bloklar = [re.sub(r"\s+", " ", m.group(0)).strip()
               for m in DIPNOT_BLOK.finditer(govde)]
    if not bloklar:
        return govde, []
    return DIPNOT_BLOK.sub("\n", govde), bloklar


# Danıştay karar künyesi — olay özetinde göstermek için
KARAR_KUNYE = re.compile(
    r"(Danıştay[^)\n]{0,60}?(?:E\.?\s*:?\s*\d{4}/\d+)[^)\n]{0,30})", re.IGNORECASE)
AYM_KUNYE = re.compile(
    r"(Anayasa\s+Mahkemesi[^)\n]{0,90}?E\.?\s*:?\s*\d{4}/\d+[^)\n]{0,40})",
    re.IGNORECASE)

DURUM_ADI = {
    "yururlukte": "yürürlükte",
    "mulga": "mülga",
    "iptal": "iptal (AYM)",
    "yurutme_durduruldu": "yürütmesi durduruldu",
}


def _sade(s):
    """Madde gövdesinin hash'i için: boşluk yığınlarını tek boşluğa indirger.
    pdftotext -layout sütun hizalaması için değişken boşluk üretir; ham gövde
    hash'lenirse yalnız sayfa kırılması bile 'madde değişti' derdi."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).strip()


def govde_siniri(metin):
    """Gövdenin bittiği konum — kuyruk dizinleri buradan sonra başlar."""
    m = KUYRUK.search(metin)
    return m.start() if m else len(metin)


def madde_durumu(govde):
    """Bir maddenin gövdesinden durumunu çıkarır.
    Sıra önemlidir: yürütme durdurma ve iptal, mülgadan SONRA bakılır ki
    'mülga edilmiş ama iptal şerhi de taşıyan' maddede güncel hâl kazansın."""
    durum = "yururlukte"
    if MULGA.search(govde[:200]):
        durum = "mulga"
    if YD.search(govde):
        durum = "yurutme_durduruldu"
    if IPTAL_AYM.search(govde):
        durum = "iptal"
    return durum


def envanter(metin):
    """Metinden madde envanteri çıkarır.

    -> (envanter, mukerrer)
       envanter: {"17": {sha, uzunluk, satir, durum, dipnot, kunye}, ...}
       mukerrer: aynı anahtarın birden çok kez görüldüğü durumlar (ilk geçen
                 esas alınır; sayı raporlanır ki sessiz veri kaybı olmasın).
    """
    son = govde_siniri(metin)
    govde = metin[:son]
    isaret = list(MADDE.finditer(govde))
    env, mukerrer = {}, []

    for i, m in enumerate(isaret):
        ham = (m.group("on") or "").lower()
        on = ("Ek " if ham.startswith("ek") else
              "Geçici " if ham.startswith("geç") else
              "Mükerrer " if ham.startswith("mük") else "")
        harf = f"/{m.group('harf')}" if m.group("harf") else ""
        anahtar = f"{on}{m.group('no')}{harf}"

        bit = isaret[i + 1].start() if i + 1 < len(isaret) else son
        ham_g = govde[m.start():bit]
        # Ö-10: hash TEMİZ gövdeden alınır; dipnotlar ayrı saklanır.
        g, dipnot_blok = dipnot_ayir(ham_g)

        if anahtar in env:
            mukerrer.append(anahtar)
            continue

        kunye = ""
        # Künye ve durum HAM gövdeden okunur: "yürütmesi durdurulan" şerhi
        # dipnotta da geçebilir ve o bilgi atılmamalı.
        k = KARAR_KUNYE.search(ham_g) or AYM_KUNYE.search(ham_g)
        if k:
            kunye = re.sub(r"\s+", " ", k.group(1)).strip()

        env[anahtar] = {
            "sha": hashlib.sha256(_sade(g).encode("utf-8")).hexdigest()[:16],
            "uzunluk": len(_sade(g)),
            "satir": govde.count("\n", 0, m.start()) + 1,
            "durum": madde_durumu(ham_g),
            "dipnot": sorted({re.sub(r"\s+", " ", d) for d in DIPNOT.findall(ham_g)})[:6],
            "dipnot_blok": dipnot_blok[:4],
            "kunye": kunye,
        }
    return env, mukerrer


# ── Olay üretimi ────────────────────────────────────────────────────────────
# Şiddet, kullanıcının 19.09.2026 kararına göre: kritik+önemli bildirim üretir,
# bilgi yalnız arayüzde görünür.
SIDDET = {
    "madde_kaldirildi":        "kritik",
    "madde_mulga":             "kritik",
    "madde_iptal":             "kritik",
    "yurutme_durduruldu":      "kritik",
    "yurutme_durdurma_kalkti": "kritik",
    "madde_eklendi":           "onemli",
    "madde_degisti":           "onemli",   # kritik_madde ise kritiğe yükseltilir
    "metin_degisti":           "bilgi",
}

OLAY_ADI = {
    "madde_eklendi":           "madde eklendi",
    "madde_kaldirildi":        "madde metinden kaldırıldı",
    "madde_degisti":           "madde metni değişti",
    "madde_mulga":             "madde mülga edildi",
    "madde_iptal":             "madde Anayasa Mahkemesi'nce iptal edildi",
    "yurutme_durduruldu":      "YÜRÜTMESİ DURDURULDU",
    "yurutme_durdurma_kalkti": "yürütme durdurma kalktı",
    "metin_degisti":           "metin değişti (madde envanteri aynı)",
}


def karsilastir(eski_env, yeni_env, kritik_madde=()):
    """İki envanteri karşılaştırır -> olay listesi.

    Durum geçişi, salt içerik değişikliğinden ÖNCE değerlendirilir: bir madde
    hem yürütmesi durdurulup hem metni değişmişse olay 'yurutme_durduruldu'dur,
    'madde_degisti' değildir — kullanıcıyı ilgilendiren asıl olgu odur.
    """
    kritik = {str(k) for k in kritik_madde}
    olaylar = []

    for anahtar in sorted(set(yeni_env) - set(eski_env), key=_sirala):
        y = yeni_env[anahtar]
        olaylar.append(_olay("madde_eklendi", anahtar, y,
                             ozet=f"m.{anahtar} eklendi"
                                  + (f" — {DURUM_ADI[y['durum']]}"
                                     if y["durum"] != "yururlukte" else "")))

    for anahtar in sorted(set(eski_env) - set(yeni_env), key=_sirala):
        e = eski_env[anahtar]
        olaylar.append(_olay("madde_kaldirildi", anahtar, e,
                             ozet=f"m.{anahtar} metinden kaldırıldı "
                                  f"(önceki durum: {DURUM_ADI[e['durum']]})"))

    for anahtar in sorted(set(eski_env) & set(yeni_env), key=_sirala):
        e, y = eski_env[anahtar], yeni_env[anahtar]
        ed, yd = e["durum"], y["durum"]

        if ed != yd:
            if yd == "yurutme_durduruldu":
                tur = "yurutme_durduruldu"
                ozet = f"m.{anahtar} — Danıştay yürütmeyi durdurdu"
                if y["kunye"]:
                    ozet += f" · {y['kunye']}"
            elif ed == "yurutme_durduruldu":
                tur = "yurutme_durdurma_kalkti"
                ozet = (f"m.{anahtar} — yürütme durdurma kalktı, "
                        f"madde yeniden {DURUM_ADI[yd]}")
            elif yd == "iptal":
                tur = "madde_iptal"
                ozet = f"m.{anahtar} — Anayasa Mahkemesi iptali"
                if y["kunye"]:
                    ozet += f" · {y['kunye']}"
            elif yd == "mulga":
                tur = "madde_mulga"
                ozet = f"m.{anahtar} mülga edildi"
                if y["dipnot"]:
                    ozet += f" · {y['dipnot'][0]}"
            else:
                tur = "madde_degisti"
                ozet = (f"m.{anahtar} durumu değişti: "
                        f"{DURUM_ADI[ed]} → {DURUM_ADI[yd]}")
            olaylar.append(_olay(tur, anahtar, y, ozet=ozet))

        elif e["sha"] != y["sha"]:
            fark = y["uzunluk"] - e["uzunluk"]
            yon = "uzadı" if fark > 0 else ("kısaldı" if fark < 0 else "yeniden yazıldı")
            ozet = f"m.{anahtar} metni değişti ({yon} {abs(fark)} karakter)"
            yeni_dipnot = [d for d in y["dipnot"] if d not in e["dipnot"]]
            if yeni_dipnot:
                ozet += f" · yeni şerh: {yeni_dipnot[0]}"
            o = _olay("madde_degisti", anahtar, y, ozet=ozet)
            if anahtar in kritik:
                o["siddet"] = "kritik"
                o["kritik_madde"] = True
            olaylar.append(o)

    return olaylar


def _sirala(anahtar):
    """'17' < '98/A' < 'Ek 3' < 'Geçici 12' sıralaması için."""
    on = 0
    for ek, ag in (("Mükerrer ", 1), ("Ek ", 2), ("Geçici ", 3)):
        if anahtar.startswith(ek):
            on, anahtar = ag, anahtar[len(ek):]
            break
    sayi = re.match(r"(\d+)", anahtar)
    return (on, int(sayi.group(1)) if sayi else 0, anahtar)


def _olay(tur, madde, bilgi, ozet):
    return {
        "tur": tur,
        "tur_adi": OLAY_ADI[tur],
        "siddet": SIDDET[tur],
        "madde": madde,
        "ozet": ozet,
        "satir": bilgi.get("satir"),
        "durum": bilgi.get("durum"),
        "kunye": bilgi.get("kunye", ""),
    }


def ozet_sayim(env):
    """Envanterin durum dağılımı — arayüzdeki rozetler için."""
    s = {}
    for v in env.values():
        s[v["durum"]] = s.get(v["durum"], 0) + 1
    return s


if __name__ == "__main__":
    import sys
    import os
    for yol in sys.argv[1:]:
        with open(yol, encoding="utf-8") as f:
            env, muk = envanter(f.read())
        print(f"\n{os.path.basename(yol)} — {len(env)} madde · mükerrer {len(muk)}")
        print("  ", ozet_sayim(env))
        for k, v in env.items():
            if v["durum"] != "yururlukte":
                print(f"   m.{k:<12} {DURUM_ADI[v['durum']]:<24} {v['kunye'][:60]}")
