#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
degisiklik.py — değişiklik raporu: numaralı liste + tek değişikliğin detay paketi

    python3 mevzuat.py degisiklikler [--kuru]    ★ sondan geriye liste, dört grup
                                                 (--kuru: "son rapor" işareti ilerlemez)
    python3 mevzuat.py degisiklikler --son       son listeyi AYNI numaralarla yeniden bas
    python3 mevzuat.py degisiklik <no> [--tam]   ★ o numaranın detay paketi

NEDEN VAR: değişiklikler iki ayrı yerde birikiyor — madde olayları
`gunluk.json`'da, Resmî Gazete kayıtları `kayit/rg-gorulen.json`'da — ve
arayüz yalnız birincisini gösteriyor. Bu modül ikisini TEK zaman çizelgesinde
birleştirir, numaralar ve "en son ne zaman rapor aldım"ı hatırlar.

DÖRT GRUP (madde değişiklikleri ve AYM kararları ayrı — kullanıcı kararı 25.09.2026):
  A · son rapordan sonra gelenlerin HEPSİ          C · AYM kararı, son rapordan sonra (hepsi)
  B · daha öncekilerden en yeni 10 tanesi          D · AYM kararı, daha önce (en yeni 10)
AYM kalemlerinde karar metninden konu + sonuç özeti çıkarılır (aym_ozeti).
Numaralar A'dan D'ye kesintisiz sürer ve `kayit/rapor-durum.json`'a yazılır;
"5'i detaylandır" başka bir oturumda da aynı değişikliği bulur.

"YENİ" ZAMANA DEĞİL KİMLİĞE GÖRE BELİRLENİR: RG taraması 3 günlük pencereyle
koşar, iki gün önceki bir yayım bugün ilk kez görülebilir. Zaman damgasıyla
karşılaştırılsaydı son rapordan ÖNCE tarihli ama SONRA görülen kayıt
hiçbir grupta görünmeden kaybolurdu.

Salt okunur: gunluk.json / durum.json / kaynak.json'a dokunmaz. Yazdığı
dosyalar kayit/rapor-durum.json ve kayit/rg-belge/ önbelleği (ikisi de git dışı).
"""
import glob
import html
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
import urllib.request
from datetime import datetime

import analiz
import cekirdek as c
import motor

KAYIT_DIR = os.path.join(motor.KOK, "kayit")
RAPOR_DURUM = os.path.join(KAYIT_DIR, "rapor-durum.json")
RG_GORULEN = os.path.join(KAYIT_DIR, "rg-gorulen.json")

ONCEKI_SAYI = 10       # B grubunda gösterilecek eski değişiklik sayısı (kullanıcı kararı)
BAYAT_SAAT = 36        # günlük iş 09:00'da koşar; bundan eskiyse koşmamış olabilir

IKON = {"kritik": "🔴", "onemli": "🟡", "bilgi": "⚪"}
CIZGI = "─" * 82

# ANAYASA MAHKEMESİ KARARLARI AYRI GRUPTA listelenir (kullanıcı kararı,
# 25.09.2026). Günde 3-5 tane çıkıyorlar; madde değişiklikleriyle aynı listede
# B grubunun 10 yerini çalıyorlardı — ilk ölçümde 18 RG kaydının 14'ü AYM
# kararıydı (9 bireysel başvuru, 5 norm denetimi). Ayrı grupta her karar TEK
# TEK numaralanır ve konu/sonuç özetiyle gösterilir; kullanıcı ilgilendiğini
# seçip detay ister.
#   norm denetimi   "… E: 2026/71, K: 2026/148 Sayılı Kararı"  → iptal getirebilir
#   bireysel başvuru "… 2021/10952 Başvuru Numaralı Kararı"    → hak ihlali
#                    tespitidir, normu değiştirmez → "bilgi" gösterilir
AYM = "anayasa mahkemesi"
BIREYSEL = "başvuru numaralı"


# ─────────────────────────────────────────────────── kalemler
def _kaynak():
    # cekirdek.kaynak(): kaynak.json + (varsa) git dışı kaynak-notlar.json
    # birleşik. `_atif_kokleri` oradan gelir.
    return c.kaynak() or {"mevzuat": []}


def _kritik_mi(kaynak_m, madde):
    return bool(madde) and str(madde) in {str(x) for x in kaynak_m.get("kritik_madde", [])}


def _gun(iso_tarih):
    """'2026-09-25' -> '25.09.2026'"""
    y, a, g = iso_tarih.split("-")
    return f"{g}.{a}.{y}"


def olay_kalemleri(gunluk, kaynak):
    km = {m["slug"]: m for m in kaynak.get("mevzuat", [])}
    kalemler = []
    for o in gunluk.get("olaylar", []):
        m = km.get(o.get("slug"), {})
        kalemler.append({
            "kimlik": o["id"], "anahtarlar": [o["id"]], "kaynak": "mevzuat",
            "zaman": o.get("zaman", ""), "tarih": o.get("tarih", ""),
            "siddet": o.get("siddet", "bilgi"), "slug": o.get("slug", ""),
            "baslik": o.get("ad", o.get("slug", "")),
            "ozet": o.get("ozet", ""), "madde": o.get("madde", ""),
            # olay kaydındaki bayrak yalnız madde_degisti'de yazılıyor; durum
            # geçişlerinde (ör. YD kalktı) yok — bu yüzden kaynak.json'dan okunur
            "kritik_madde": _kritik_mi(m, o.get("madde")),
        })
    return kalemler


def rg_kalemleri(anahtarlar, izlenen):
    """rg-gorulen.json anahtarlarından ('YYYY-AA-GG|başlık') kalem üretir.

    Kayıtta yalnız tarih ve başlık saklanıyor; sebep ve şiddet `rg.suz()` ile
    başlıktan YENİDEN hesaplanır. Kategori bilinmediği için sebebi yalnız
    kategoriden gelen bir kayıt 'çözülemedi' der — detayda fihrist yeniden
    çekildiğinde tam sebep görünür."""
    import rg as rgm
    kalemler = []
    for a in anahtarlar:
        tarih, _, baslik = a.partition("|")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", tarih):
            continue
        s = rgm.suz([{"bolum": "", "kategori": "", "baslik": baslik,
                      "url": "", "ilan": False}], izlenen)
        sebep, siddet = ((s[0]["sebep"], s[0]["siddet"]) if s else
                         (["sebep başlıktan çözülemedi — detayda fihristten okunur"],
                          "onemli"))
        kb = c.tr_kucult(baslik)
        aym = ("bireysel" if BIREYSEL in kb else "norm") if kb.startswith(AYM) else ""
        if aym == "bireysel":
            siddet = "bilgi"
        izl = next((x.split(":", 1)[1].split("(")[0].strip()
                    for x in sebep if x.startswith("izlenen:")), "")
        kalemler.append({
            "kimlik": f"RG-{tarih}-{c.sha(baslik)[:8]}", "anahtarlar": [a],
            "kaynak": "rg", "zaman": f"{tarih}T00:00:00",
            "tarih": _gun(tarih), "rg_tarih": tarih, "siddet": siddet,
            "slug": izl, "baslik": baslik, "ozet": " · ".join(sebep),
            "madde": "", "kritik_madde": False, "aym": aym,
        })
    return kalemler


def tum_kalemler():
    """Bütün değişiklikler, EN YENİ ÖNCE."""
    kaynak = _kaynak()
    kalemler = olay_kalemleri(c.yukle(motor.GUNLUK, {"olaylar": []}), kaynak)
    kalemler += rg_kalemleri(c.yukle(RG_GORULEN, {"anahtarlar": []})["anahtarlar"],
                             kaynak.get("mevzuat", []))
    return sorted(kalemler, key=lambda k: (k["zaman"], k["kimlik"]), reverse=True)


def grupla(kalemler, raporlanan, onceki_sayi=ONCEKI_SAYI):
    """-> (yeni, onceki). Tek bir alt kaydı bile raporlanmamış kalem YENİDİR
    (birden çok alt kayıt taşıyan kalem sonradan büyürse yeniden görünür)."""
    raporlanan = set(raporlanan)
    yeni = [k for k in kalemler if any(a not in raporlanan for a in k["anahtarlar"])]
    kimlik = {k["kimlik"] for k in yeni}
    onceki = [k for k in kalemler if k["kimlik"] not in kimlik][:onceki_sayi]
    return yeni, onceki


# ─────────────────────────────────────────────────── tazelik
def _tazelik():
    """-> (son denetim, son RG taraması, uyarı listesi)"""
    son_den = None
    for d in c.yukle(motor.DURUM).values():
        try:
            t = datetime.strptime(d.get("son_dogrulama", ""), "%d.%m.%Y %H:%M")
        except ValueError:
            continue
        son_den = max(son_den, t) if son_den else t
    son_rg = None
    try:
        son_rg = datetime.fromisoformat(c.yukle(RG_GORULEN).get("son_tarama", ""))
    except ValueError:
        pass
    uyari = []
    simdi = datetime.now()
    for ad, t in (("mevzuat.gov.tr denetimi", son_den), ("Resmî Gazete taraması", son_rg)):
        if t is None:
            uyari.append(f"{ad} hiç koşmamış görünüyor")
        elif (simdi - t).total_seconds() > BAYAT_SAAT * 3600:
            uyari.append(f"{ad} {t:%d.%m.%Y %H:%M}'den beri koşmadı — "
                         f"günlük iş (launchd 09:00) aksamış olabilir; liste eksik olabilir")
    return son_den, son_rg, uyari


# ─────────────────────────────────────────────────── AYM özeti
def _kisa_aym(baslik):
    """'Anayasa Mahkemesinin 25/6/2026 Tarihli ve E: 2026/71, K: 2026/148 Sayılı
    Kararı' -> '25/6/2026 · E: 2026/71, K: 2026/148'"""
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{4}) Tarihli ve (.+?) (?:Sayılı|Başvuru Numaralı)",
                  baslik)
    return f"{m.group(1)} · {m.group(2)}" if m else baslik


def _duz(t, imza_kes=False):
    """OCR kopyasındaki sayfa başlıklarını atıp tek satıra indirger. imza_kes:
    HÜKÜM'den sonraki "Başkan | Üye" imza tablosunu at (yalnız HÜKÜM için —
    bireysel başvuruda aynı tablo 1. sayfadaki künyede de var)."""
    t = re.sub(r"(?m)^## Sayfa \d+\s*$", " ", t)
    if imza_kes:
        t = re.sub(r"(?s)\b(Başkan|Üye)\s*\|.*$", " ", t)
    return " ".join(t.split())


def _buyuk(s):
    """Hüküm fıkrasının belirleyici kelimeleri BÜYÜK harfle yazılır ("İHLAL
    EDİLDİĞİNE", "REDDİNE"); aynı kelimeler küçük harfle iddiaları da anlatır
    ("…ihlal edildiğine ilişkin iddianın KABUL EDİLEBİLİR OLDUĞUNA") — bu yüzden
    eşleşme BÜYÜK HARFE DUYARLIDIR. OCR Türkçe harfleri düşürebildiği için
    ("OLDUGUNA", "REDDINE" — ölçüldü) her Türkçe harf ASCII eşiyle de kabul edilir."""
    for tr, en in (("İ", "Ii"), ("Ğ", "G"), ("Ü", "U"), ("Ö", "O"), ("Ş", "S"), ("Ç", "C")):
        s = s.replace(tr, f"[{tr}{en}]")   # "iHLAL EDİLDiĞiNE" de basılıyor (ölçüldü)
    return re.compile(s)


SONUC_NORM = ((_buyuk("İPTALİNE"), "İPTAL"),
              (_buyuk("REDDİNE"), "RET"),
              (_buyuk("YER OLMADIĞINA"), "KARAR VERİLMESİNE YER YOK"))
SONUC_BIREYSEL = ((_buyuk("İHLAL EDİLDİĞİNE"), "İHLAL VAR"),
                  (_buyuk("İHLAL EDİLMEDİĞİNE"), "İHLAL YOK"),
                  (_buyuk("KABUL EDİLEMEZ OLDUĞUNA"), "bir kısım iddia KABUL EDİLEMEZ"),
                  (_buyuk("DÜŞMESİNE"), "DÜŞME"))


def aym_ozeti(metin, tur):
    """AYM kararının metninden -> (konu, sonuç).

    Norm denetiminde konunun en güvenilir kaynağı HÜKÜM'ün kendisidir: hangi
    kanunun hangi maddesi, iptal mi ret mi — tek cümlede. İlk sayfadaki
    "İTİRAZIN KONUSU" iki sütunlu dizgi yüzünden OCR'da karışıyor (ölçüldü,
    20260918-15: "İTİRAZIN KONUSU: 4/12/2004 tarihli / sürülerek iptaline").
    Bireysel başvuruda konu "BAŞVURUNUN ÖZETİ"nin 1. paragrafıdır
    ("1. Başvuru, … iddialarına ilişkindir.")."""
    # OCR (macOS Vision) ayrışık Unicode basabiliyor (g + birleşik breve);
    # NFC'ye çevrilmezse "Ğ" içeren hiçbir desen eşleşmez.
    metin = unicodedata.normalize("NFC", metin)
    hk = list(HUKUM.finditer(metin))
    hukum = _duz(metin[hk[-1].end():], imza_kes=True)[:2500] if hk else ""
    hukum = " ".join(hukum.replace("|", " ").split())   # OCR tablo ayracı
    sonuclar = [ad for desen, ad in (SONUC_NORM if tur == "norm" else SONUC_BIREYSEL)
                if desen.search(hukum)]
    if tur == "norm" and "İPTAL" in sonuclar and len(sonuclar) > 1:
        sonuclar.insert(0, "KISMEN")
    if tur == "norm" and "yürürlüğe girmesine" in c.tr_kucult(hukum):
        sonuclar.append("iptalin yürürlüğü ERTELENDİ")
    sonuc = " · ".join(dict.fromkeys(sonuclar)) or "hüküm okunamadı"

    if tur == "norm":
        # konu = hükmün ilk bölümü, ilk belirleyici kelimeye (REDDİNE/İPTALİNE…)
        # kadar; sonrasında karşıoy yazan üye adları geliyor
        bit = min((m.end() for d, _ in SONUC_NORM for m in [d.search(hukum)] if m),
                  default=len(hukum))
        konu = hukum[:bit]
        konu = konu[:320] + ("…" if len(konu) > 320 else "")
    else:
        d = _duz(metin)
        m = re.search(r"1\s*\.\s*Başvuru[,;:]?\s*(.{20,600}?ilişkindir\.)", d)
        konu = (m.group(1) if m else
                d[d.find("ÖZETİ") + 5:][:300] if "ÖZETİ" in d else "")
        konu = konu[:320] + ("…" if len(konu) > 320 else "")
    return konu.strip() or "konu okunamadı", sonuc


# Sonuç işareti (kullanıcı kararı 26.09.2026): tabloda göz ilk bakışta
# "bir şey bulundu mu" sorusunu yakalasın. Karışık hükümde (ör. "İHLAL VAR ·
# bir kısım iddia KABUL EDİLEMEZ") BAŞTAKİ, yani asıl sonuç belirler.
ISARET = (("İHLAL VAR", "❗"), ("İPTAL", "❗"),
          ("İHLAL YOK", "✖️"), ("RET", "✖️"), ("KABUL EDİLEMEZ", "✖️"),
          ("KARAR VERİLMESİNE YER YOK", "➖"), ("DÜŞME", "➖"))
ISARET_ACIKLAMA = ("❗ ihlal bulundu / kural iptal edildi · ✖️ ret / ihlal yok / kabul "
                   "edilemez · ➖ karar verilmesine yer yok / düşme · ❔ okunamadı")


def sonuc_isareti(sonuc):
    for parca in sonuc.split(" · "):
        for anahtar, isaret in ISARET:
            if anahtar in parca:
                return isaret
    return "❔"


def saglik_mi(*metinler):
    """AYM kararının konusu sağlıkla ilgili mi — rg.py'nin RG fihristi için
    kalibre ettiği SAĞLIK/GÜRÜLTÜ süzgeci konu cümlesine uygulanır. Karar
    metninin tamamına UYGULANMAZ: cezaevi ya da iş davası kararında geçen
    "sağlık raporu" gibi yan ifadeler sahte 🩺 üretirdi."""
    import rg as rgm
    t = c.tr_kucult(" ".join(metinler))
    return bool(rgm.SAGLIK.search(t)) and not bool(rgm.GURULTU.search(t))


def rg_kaydi(k):
    """RG kaleminin fihrist kaydı -> {baslik, url, bolum, kategori, sayi}.

    Geçmiş günlerin fihristi değişmez: kayit/rg-belge/fihrist/<tarih>.json'da
    önbelleğe alınır (bugünün fihristi alınmaz — gün içinde mükerrer sayı
    eklenebilir). Yayın sayfaları her üretimde RG'ye gitmesin diye var."""
    import rg as rgm
    tarih = k["rg_tarih"]
    yol = os.path.join(RG_BELGE_DIR, "fihrist", f"{tarih}.json")
    veri = c.yukle(yol) if os.path.exists(yol) else None
    if not veri:
        sayi, kayitlar, hata = rgm.fihrist(tarih)
        if hata:
            raise RuntimeError(f"fihrist: {hata}")
        veri = {"sayi": sayi, "kayitlar": kayitlar}
        if tarih < datetime.now().strftime("%Y-%m-%d"):
            os.makedirs(os.path.dirname(yol), exist_ok=True)
            c.kaydet(yol, veri)
    baslik = k["anahtarlar"][0].partition("|")[2]
    rec = next((r for r in veri["kayitlar"] if r["baslik"][:120] == baslik), None)
    if not rec or not rec.get("url"):
        raise RuntimeError("fihristte bulunamadı")
    return dict(rec, sayi=veri["sayi"])


def aym_ozetleri(kalemler):
    """Her AYM kalemine konu/sonuç ekler. Belgeler kayit/rg-belge/'den okunur;
    ilk görülende indirilip gerekirse OCR'lanır (karar başına ~5-30 sn)."""
    for i, k in enumerate(kalemler, 1):
        try:
            rec = rg_kaydi(k)
            k["rg_url"] = rec["url"]
            ad = os.path.splitext(rec["url"].rsplit("/", 1)[-1])[0]
            if not os.path.exists(os.path.join(RG_BELGE_DIR, ad + ".txt")):
                print(f"  AYM kararı okunuyor ({i}/{len(kalemler)}) {ad}…",
                      file=sys.stderr, flush=True)
            metin, yontem = rg_belge_metni(rec["url"])
            k["aym_konu"], k["aym_sonuc"] = aym_ozeti(metin, k["aym"])
            k["aym_ocr"] = yontem.startswith("OCR")
        except Exception as e:
            k["aym_konu"], k["aym_sonuc"] = f"(özet alınamadı: {e})", "?"
            k["aym_ocr"] = False
        k["aym_isaret"] = sonuc_isareti(k["aym_sonuc"])
        k["saglik"] = saglik_mi(k["aym_konu"]) if "okunamadı" not in k["aym_konu"] else False


# ─────────────────────────────────────────────────── liste
def _satir(no, k):
    ikon = IKON.get(k["siddet"], "·")
    if k.get("aym"):
        tur = "norm denetimi" if k["aym"] == "norm" else "bireysel başvuru"
        saglik = "🩺 SAĞLIK · " if k.get("saglik") else ""
        s = (f"{no:>3}. {ikon} {k['tarih']} · 📰 AYM · {saglik}{tur} · {_kisa_aym(k['baslik'])}")
        if "aym_konu" in k:
            s += (f"\n       konu : {k['aym_konu']}"
                  f"\n       sonuç: {k.get('aym_isaret', '')} {k['aym_sonuc']}"
                  + ("  (OCR)" if k.get("aym_ocr") else ""))
        return s
    if k["kaynak"] == "rg":
        ust = f"{k['tarih']} · 📰 RG"
    else:
        ust = f"{k['tarih']} · ⚖️ mevzuat.gov.tr"
    ek = "  ★ kritik madde" if k.get("kritik_madde") else ""
    ozet = k["ozet"] if len(k["ozet"]) <= 160 else k["ozet"][:157].rstrip() + "…"
    return (f"{no:>3}. {ikon} {ust}\n"
            f"       {k['baslik']}\n"
            f"       → {ozet}{ek}")


def _son_liste_gruplari(durum, kalemler):
    """Kaydedilmiş son listeyi aynı numara sırasıyla gruplara geri kurar."""
    harita = {k["kimlik"]: k for k in kalemler}
    gruplar = {"yeni": [], "onceki": [], "aym-yeni": [], "aym-onceki": []}
    for x in sorted(durum.get("liste") or [], key=lambda x: x["no"]):
        if x["kimlik"] in harita:
            gruplar.setdefault(x["grup"], []).append(harita[x["kimlik"]])
    return gruplar


def komut_liste(kuru=False, aym_ozet=True, son=False):
    """son=True: YENİ liste üretmez — en son listeyi AYNI numaralarla yeniden
    basar (işaret ilerlemez, numara eşlemesi değişmez). Biçim değiştiğinde ya
    da kullanıcı "listeyi tekrar göster" dediğinde kullanılır."""
    kalemler = tum_kalemler()
    durum = c.yukle(RAPOR_DURUM, {})
    if son:
        if not durum.get("liste"):
            print("Kayıtlı liste yok — önce: python3 mevzuat.py degisiklikler")
            return 2
        g = _son_liste_gruplari(durum, kalemler)
        yeni, onceki, aym_yeni, aym_onceki = (g["yeni"], g["onceki"],
                                              g["aym-yeni"], g["aym-onceki"])
        kuru = True
        onceki_rapor = durum.get("onceki_rapor", "")
    else:
        onceki_rapor = durum.get("son_rapor", "")
        raporlanan = durum.get("raporlanan", [])
        yeni, onceki = grupla([k for k in kalemler if not k.get("aym")], raporlanan)
        aym_yeni, aym_onceki = grupla([k for k in kalemler if k.get("aym")], raporlanan)
    if aym_ozet:
        aym_ozetleri(aym_yeni + aym_onceki)
    son_den, son_rg, uyari = _tazelik()
    simdi = datetime.now()

    if son:
        print(f"\nMEVZUAT DEĞİŞİKLİK RAPORU · SON LİSTE YENİDEN — numaralar "
              f"{datetime.fromisoformat(durum['liste_zamani']):%d.%m.%Y %H:%M} tarihli listeninkidir")
    else:
        print(f"\nMEVZUAT DEĞİŞİKLİK RAPORU · {simdi:%d.%m.%Y %H:%M}"
              + ("  (KURU — 'son rapor' işareti ilerlemedi)" if kuru else ""))
    if onceki_rapor:
        print(f"Önceki rapor : {datetime.fromisoformat(onceki_rapor):%d.%m.%Y %H:%M}")
    else:
        print("Önceki rapor : YOK — ilk rapor, kayıtlı bütün değişiklikler 'yeni' sayıldı")
    print(f"Son denetim  : {f'{son_den:%d.%m.%Y %H:%M}' if son_den else '—'} (mevzuat.gov.tr)"
          f" · {f'{son_rg:%d.%m.%Y %H:%M}' if son_rg else '—'} (Resmî Gazete)")
    for u in uyari:
        print(f"⚠ {u}")
    print(CIZGI)

    liste, no = [], 0
    for baslik, grup, etiket, bos in (
            (f"A · SON RAPORDAN SONRA — {len(yeni)} değişiklik", yeni, "yeni",
             "Son rapordan beri yeni değişiklik yok."),
            (f"B · DAHA ÖNCE — en yeni {len(onceki)}", onceki, "onceki", "(yok)"),
            (f"C · ANAYASA MAHKEMESİ KARARLARI · son rapordan sonra — {len(aym_yeni)}",
             aym_yeni, "aym-yeni", "Son rapordan beri yeni AYM kararı yok."),
            (f"D · ANAYASA MAHKEMESİ KARARLARI · daha önce — en yeni {len(aym_onceki)}",
             aym_onceki, "aym-onceki", "(yok)")):
        print(f"\n{baslik}\n")
        if not grup:
            print(f"     {bos}")
        for k in grup:
            no += 1
            print(_satir(no, k))
            liste.append({"no": no, "kimlik": k["kimlik"], "grup": etiket})
    if aym_yeni or aym_onceki:
        print(f"\nAYM işaretleri: {ISARET_ACIKLAMA} · 🩺 konu sağlıkla ilgili")
    print(f"\n{CIZGI}\nDetay: python3 mevzuat.py degisiklik <no>")
    if son:
        return 0

    # Numara eşlemesi HER ZAMAN yazılır — kuru koşuda da: kullanıcı ekranda
    # gördüğü numarayı sorar, "5" o ekrandaki 5 olmalı. "Son rapor" işareti
    # (neyin görüldüğü) ise yalnız gerçek raporda ilerler.
    if not kuru:
        tum = set(raporlanan)
        for k in kalemler:
            tum.update(k["anahtarlar"])
        durum.update(son_rapor=simdi.isoformat(timespec="seconds"),
                     onceki_rapor=onceki_rapor, raporlanan=sorted(tum))
    durum.update(liste=liste, liste_zamani=simdi.isoformat(timespec="seconds"))
    os.makedirs(os.path.dirname(RAPOR_DURUM), exist_ok=True)
    c.kaydet(RAPOR_DURUM, durum)
    return 0


# ─────────────────────────────────────────────────── metin yardımcıları
def madde_metni(metin, anahtar):
    """Metinden tek maddenin gövdesini çıkarır (`mevzuat.py madde` ile aynı
    kesim). Madde yoksa None."""
    env, _ = analiz.envanter(metin)
    if anahtar not in env:
        return None
    son = analiz.govde_siniri(metin)
    govde = metin[:son]
    isaret = list(analiz.MADDE.finditer(govde))
    for i, m in enumerate(isaret):
        if govde.count("\n", 0, m.start()) + 1 == env[anahtar]["satir"]:
            bit = isaret[i + 1].start() if i + 1 < len(isaret) else son
            return re.sub(r"\n{3,}", "\n\n", govde[m.start():bit]).rstrip()
    return None


HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def geri_kur(yeni, fark):
    """Unified diff'i TERSİNE uygulayarak eski nüshayı kurar.

    Satırlar iki tarafta da `splitlines(keepends=True)` ile bölünür — motor.yaz()
    farkı tam olarak böyle üretti. Bağlam satırı tutmazsa ValueError: yanlış
    nüshaya uygulanan fark sessizce çöp üretmesin."""
    ys = yeni.splitlines(keepends=True)
    fs = fark.splitlines(keepends=True)
    cikti, poz, i = [], 0, 0
    while i < len(fs):
        m = HUNK.match(fs[i])
        if not m:
            i += 1
            continue
        bas, say = int(m.group(3)), int(m.group(4) or 1)
        bas = bas - 1 if say else bas
        if bas < poz:
            raise ValueError("blok sırası bozuk")
        cikti.extend(ys[poz:bas])
        poz = bas
        i += 1
        while i < len(fs) and not fs[i].startswith("@@"):
            s = fs[i]
            if s[:1] in (" ", "+"):
                if poz >= len(ys) or ys[poz] != s[1:]:
                    raise ValueError(f"bağlam tutmadı (satır {poz + 1})")
                if s[0] == " ":
                    cikti.append(s[1:])
                poz += 1
            elif s[:1] == "-":
                cikti.append(s[1:])
            i += 1
    cikti.extend(ys[poz:])
    return "".join(cikti)


def _fark_basligi(fark):
    """'--- slug (eski f987572a ...)' -> ('f987572a', '7b6789b3')"""
    e = re.search(r"^---[^\n]*\(eski ([0-9a-f]{8})", fark, re.M)
    y = re.search(r"^\+\+\+[^\n]*\(yeni ([0-9a-f]{8})", fark, re.M)
    return (e.group(1) if e else ""), (y.group(1) if y else "")


def fark_dosyasi(olay):
    """Olayın fark dosyası; olay kaydında yoksa (elle işlenen geçiş olayı)
    o belgenin olaydan önceki en son fark dosyası."""
    if olay.get("fark_dosyasi"):
        yol = os.path.join(motor.KOK, olay["fark_dosyasi"])
        return yol if os.path.exists(yol) else None
    gun = (olay.get("zaman") or "9999")[:10]
    aday = sorted(y for y in glob.glob(os.path.join(motor.ARS_DIR,
                                                    f"{olay['slug']}_*_fark.diff"))
                  if os.path.basename(y)[len(olay["slug"]) + 1:][:10] <= gun)
    return aday[-1] if aday else None


def eski_nusha(slug, fark, yeni):
    """Değişiklikten önceki tam metin. -> (metin, nereden) · bulunamazsa (None, neden)

    Sıra: 1) arsiv/ kopyası (motor.yaz() her değişiklikte bırakır, git dışı)
          2) farkı güncel nüshaya ters uygulamak (güncel = farkın yeni tarafıysa)
          3) git geçmişinde imzası tutan sürüm
    Her yolun sonucu farkın başlığındaki imzayla DOĞRULANIR."""
    eski8, yeni8 = _fark_basligi(fark)
    if not eski8:
        return None, "fark dosyasının başlığında eski nüshanın imzası yok"

    for yol in glob.glob(os.path.join(motor.ARS_DIR, f"{slug}_*_{eski8}.txt")):
        with open(yol, encoding="utf-8") as f:
            t = f.read()
        if c.sha(t)[:8] == eski8:
            return t, f"arşiv nüshası {os.path.relpath(yol, motor.KOK)} (imza {eski8} ✓)"

    if c.sha(yeni)[:8] == yeni8:
        try:
            t = geri_kur(yeni, fark)
            dogru = "✓" if c.sha(t)[:8] == eski8 else "imza tutmadı, bağlam tuttu"
            return t, f"fark dosyası güncel nüshaya ters uygulanarak kuruldu ({dogru})"
        except ValueError:
            pass

    try:
        r = subprocess.run(["git", "log", "--format=%H", "--", f"metin/{slug}.txt"],
                           capture_output=True, text=True, cwd=motor.KOK, timeout=20)
        for h in r.stdout.split():
            g = subprocess.run(["git", "show", f"{h}:metin/{slug}.txt"],
                               capture_output=True, cwd=motor.KOK, timeout=20)
            t = g.stdout.decode("utf-8", "replace")
            if g.returncode == 0 and c.sha(t)[:8] == eski8:
                return t, f"git geçmişi {h[:8]} (imza {eski8} ✓)"
    except (OSError, subprocess.SubprocessError):
        pass

    neden = (f"eski nüsha ({eski8}) arşivde de git'te de yok")
    if yeni8 and c.sha(yeni)[:8] != yeni8:
        neden += (f"; güncel nüsha ({c.sha(yeni)[:8]}) farkın yeni tarafı ({yeni8}) "
                  f"değil, fark ters uygulanamadı")
    return None, neden


def ilgili_bloklar(fark, bas, bit, madde_metni_=""):
    """Farkın bu maddeye düşen blokları.

    İki ölçüt: (1) YENİ tarafta [bas, bit) satır aralığına değmek, (2) bağlam
    ya da eklenen satırlardan birinin maddenin güncel metninde birebir geçmesi.
    İkincisi şart: elle işlenen geçiş farkında (19.09.2026, y-ozel-hastaneler)
    farkın yeni tarafı güncel nüsha değil, satır numaraları ~5 satır kayık ve
    yalnız aralığa bakınca asıl değişen fıkranın bloğu kaçıyordu."""
    tanidik = {" ".join(x.split()) for x in madde_metni_.splitlines()
               if len(x.strip()) > 30}
    bloklar, simdiki, aralikta = [], None, False

    def kapat():
        if simdiki and (aralikta or any(
                " ".join(x[1:].split()) in tanidik
                for x in simdiki[1:] if x[:1] in (" ", "+"))):
            bloklar.append("\n".join(simdiki))

    for s in fark.splitlines():
        m = HUNK.match(s)
        if m:
            kapat()
            y1 = int(m.group(3))
            y2 = y1 + int(m.group(4) or 1)
            simdiki, aralikta = [s], (y1 < bit and y2 > bas)
        elif simdiki is not None and not s.startswith(("+++", "---")):
            simdiki.append(s)
    kapat()
    return bloklar


def _madde_araligi(env, anahtar):
    """Envanterden maddenin satır aralığı [bas, bit)."""
    if anahtar not in env:
        return None
    bas = env[anahtar]["satir"]
    sonraki = [v["satir"] for v in env.values() if v["satir"] > bas]
    return bas, (min(sonraki) if sonraki else 10 ** 9)


def _kelime_farki(a, b):
    import mevzuat as cli          # renk kodları yalnız TTY'de açılır
    return cli.kelime_farki(a, b)


def _belge_isaretleri(km):
    """Bir dosyanın BU belgeyi andığını gösteren ifadeler (Türkçe küçültülmüş).
    Çıplak 'm.12' her kanunun 12. maddesine uyar; dosyada belgenin adı ya da
    kanun numarası da geçiyorsa atıf büyük olasılıkla bu belgeyedir."""
    ad = c.tr_kucult(re.sub(r"\s*\(.*?\)\s*", " ", km.get("ad", ""))).split()
    isaret = []
    if len(ad) >= 2:
        isaret.append(re.escape(" ".join(ad[:2])))
    if km.get("rg_anahtar"):
        isaret.append(re.escape(c.tr_kucult(km["rg_anahtar"])))
    if km.get("tur") in ("Kanun", "KHK") and km.get("no"):
        isaret.append(rf"\b{re.escape(str(km['no']))}\b")
    return re.compile("|".join(isaret)) if isaret else None


def _etki_yaz(km, madde, tam, kimlik=""):
    """etki.py taraması, iki kümeye ayrılmış: belgeyi de anan dosyalar (güçlü)
    ve yalnız çıplak madde numarası geçenler (zayıf — başka kanun olabilir).
    İlk denemede (25.09.2026, y-ayakta-teshis m.12) 150+ satırın neredeyse
    tamamı KMK m.12 ve imar m.12 gibi alakasız atıflardı."""
    import etki
    kokler = _kaynak().get("_atif_kokleri") or []
    print(f"\n── ETKİ · bu maddeye atıf yapan belgelerim (kökler: {', '.join(kokler) or '—'})")
    if not kokler:
        print("   Taranacak kök yok — `kaynak-notlar.json` içine `_atif_kokleri` ekle.")
        return
    bulgu = etki.tara(kokler, km.get("no", ""), madde, sinir=600)
    dosya = {}
    for yol, i, satir in bulgu:
        dosya.setdefault(yol, []).append((i, satir))
    desen = _belge_isaretleri(km)
    guclu, zayif = [], []
    for yol, satirlar in sorted(dosya.items()):
        try:
            with open(yol, encoding="utf-8", errors="ignore") as f:
                icerik = c.tr_kucult(f.read())
        except OSError:
            icerik = ""
        (guclu if desen and desen.search(icerik) else zayif).append((yol, satirlar))

    def kisa(yol):
        for k in kokler:
            k = os.path.expanduser(k)
            if yol.startswith(k):
                return os.path.relpath(yol, os.path.dirname(k))
        return yol

    # Bayat belge düzeltmesi dosyaya "🔄 GG.AA.YYYY'de değişti … (olay O-…)" notu
    # düşer; olay kimliği dosyada geçiyorsa bu olay orada zaten işlenmiştir.
    islenmis = set()
    if kimlik:
        for yol, _ in guclu:
            try:
                with open(yol, encoding="utf-8", errors="ignore") as f:
                    if kimlik in f.read():
                        islenmis.add(yol)
            except OSError:
                pass
    print(f"   GÜÇLÜ — belgeyi de anan {len(guclu)} dosya"
          + (f" ({len(islenmis)} tanesine bu olay 🔄 işlenmiş)" if islenmis else "") + ":")
    for yol, satirlar in (guclu if tam else guclu[:15]):
        print(f"   {kisa(yol)}  ({len(satirlar)} atıf)"
              + (f"  🔄 {kimlik} işlendi" if yol in islenmis else ""))
        for i, satir in satirlar[:3]:
            print(f"      {i:>5}: {satir}")
    if not tam and len(guclu) > 15:
        print(f"   … {len(guclu) - 15} dosya daha (--tam)")
    if not guclu:
        print("   (yok)")
    print(f"   ZAYIF — yalnız çıplak 'm.{madde}' geçen {len(zayif)} dosya "
          f"(başka kanunun maddesi olabilir):")
    for yol, satirlar in (zayif if tam else zayif[:8]):
        print(f"   · {kisa(yol)} ({len(satirlar)})")
    if not tam and len(zayif) > 8:
        print(f"   … {len(zayif) - 8} dosya daha (--tam)")
    if len(bulgu) >= 600:
        print("   ⚠ tarama 600 atıfta kesildi — liste eksik olabilir")


# ─────────────────────────────────────────────────── detay: mevzuat olayı
def _baslik_yaz(no, k, olay_turu):
    print(f"\n#{no} · {k['kimlik']} · {IKON.get(k['siddet'], '')} {k['siddet']}"
          f" · {olay_turu}")
    print(CIZGI)


def _olay_detayi(no, k, tam):
    gunluk = c.yukle(motor.GUNLUK, {"olaylar": []})["olaylar"]
    o = next(x for x in gunluk if x.get("id") == k["kimlik"])
    slug, madde = o.get("slug", ""), str(o.get("madde") or "")
    km = next((m for m in _kaynak()["mevzuat"] if m["slug"] == slug), {})
    d = c.yukle(motor.DURUM).get(slug, {})

    _baslik_yaz(no, k, o.get("tur_adi", o.get("tur", "")))
    print(f"Belge        : {o.get('ad', slug)}  ({slug})")
    print(f"Sınıf / grup : {o.get('sinif', '—')} · {', '.join(km.get('grup', [])) or '—'}")
    if madde:
        print(f"Madde        : {madde}"
              + ("  ★ kaynak.json'da KRİTİK MADDE" if _kritik_mi(km, madde) else ""))
    print(f"Tespit       : {o.get('tarih', '')} · kaynak: {o.get('kaynak', '')}")
    print(f"Olay özeti   : {o.get('ozet', '')}")
    if o.get("kunye"):
        print(f"Künye        : {o['kunye']}")
    if o.get("durum"):
        print(f"Maddenin güncel durumu (olay anında): "
              f"{analiz.DURUM_ADI.get(o['durum'], o['durum'])}")
    if o.get("not"):
        print(f"Not          : {o['not']}")
    print(f"Neden izleniyor (kaynak.json): {km.get('neden', '—')}")
    if km.get("dayanak"):
        print(f"Dayanak      : {', '.join(km['dayanak'])}")
    print(f"Resmî sayfa  : {d.get('sayfa_url', '—')}")
    print(f"Güncel nüsha : son doğrulama {d.get('son_dogrulama', '?')} · "
          f"son değişiklik {d.get('son_degisiklik', '?')}")

    kardes = [x for x in gunluk if x.get("slug") == slug and x.get("zaman") == o.get("zaman")
              and x.get("id") != o.get("id")]
    if kardes:
        print(f"\nAynı değişiklikte başka {len(kardes)} olay daha var:")
        for x in kardes:
            print(f"   · {x['id']} · {x.get('ozet', '')}")

    if o.get("tur") == "dayanak_degisti":
        dayanaklar = set(km.get("dayanak", []))
        ilgili = [x for x in gunluk if x.get("slug") in dayanaklar
                  and x.get("zaman", "")[:10] == o.get("zaman", "")[:10]]
        print(f"\n── Dayanak belgedeki olaylar ({', '.join(sorted(dayanaklar))})")
        for x in ilgili:
            print(f"   · {x['id']} · {x.get('ad', '')[:40]} · {x.get('ozet', '')}")
        print("   Bu olay bir uyarıdır: yönetmeliğin kendisi henüz değişmedi.")

    yeni_yol = os.path.join(motor.MET_DIR, slug + ".txt")
    yeni = open(yeni_yol, encoding="utf-8").read() if os.path.exists(yeni_yol) else ""
    fyol = fark_dosyasi(o)
    fark = open(fyol, encoding="utf-8").read() if fyol else ""

    if fark and d.get("son_degisiklik") not in ("—", "", None) \
            and d["son_degisiklik"] != o.get("tarih", "")[:10]:
        print(f"\n⚠ Belge bu olaydan sonra da değişmiş (son değişiklik "
              f"{d['son_degisiklik']}); 'güncel metin' sonraki değişikliği de içerir.")

    eski, nereden = (eski_nusha(slug, fark, yeni) if fark and yeni
                     else (None, "fark dosyası yok" if not fark else "güncel metin yok"))

    if madde and yeni:
        y_m = madde_metni(yeni, madde)
        e_m = madde_metni(eski, madde) if eski else None
        print(f"\n── ESKİ METİN · m.{madde} · {nereden}")
        print(e_m if e_m else ("(madde eski nüshada YOK — yeni eklenmiş)" if eski
                               else "(eski nüsha kurulamadı)"))
        print(f"\n── YENİ METİN · m.{madde} · güncel nüsha (mevzuat.gov.tr, "
              f"son doğrulama {d.get('son_dogrulama', '?')})")
        print(y_m if y_m else "(madde güncel nüshada YOK — metinden kaldırılmış)")
        if e_m and y_m:
            print(f"\n── KELİME FARKI · [-silinen-] {{+eklenen+}}")
            print(_kelime_farki(e_m, y_m) if e_m != y_m else "(gövde aynı — değişiklik "
                  "dipnot/şerh düzeyinde ya da sonraki bir değişiklikle geri alınmış)")
        elif fark and not eski:
            env, _ = analiz.envanter(yeni)
            aralik = _madde_araligi(env, madde)
            bloklar = ilgili_bloklar(fark, *aralik, y_m or "") if aralik else []
            print(f"\n── FARK DOSYASINDAN bu maddeye düşen bloklar "
                  f"({os.path.relpath(fyol, motor.KOK)})")
            print("   ⚠ YAKLAŞIK: farkın satır numaraları güncel nüshayla birebir "
                  "örtüşmeyebilir.")
            print("\n\n".join(bloklar) if bloklar else "   (satır aralığına düşen blok yok — "
                  "tüm fark için: python3 mevzuat.py fark " + slug + ")")
    elif fark:
        print(f"\n── FARK ({os.path.relpath(fyol, motor.KOK)}) — kelime düzeyi için: "
              f"python3 mevzuat.py fark {slug} --kelime")
        satirlar = fark.splitlines()
        print("\n".join(satirlar if tam else satirlar[:80]))
        if not tam and len(satirlar) > 80:
            print(f"… {len(satirlar) - 80} satır daha (--tam)")

    if fark:
        n = sum(1 for s in fark.splitlines() if HUNK.match(s))
        degisen = sum(1 for s in fark.splitlines()
                      if s[:1] in "+-" and s[:3] not in ("+++", "---"))
        print(f"\nFark dosyası: {os.path.relpath(fyol, motor.KOK)} · {n} blok · "
              f"{degisen} değişen satır (sayfa kırılması kaymaları dahil) — bu maddenin "
              f"dışındaki bloklar için: python3 mevzuat.py fark {slug} --kelime")

    if madde:
        _etki_yaz(km, madde, tam, o.get("id", ""))

    rgler = [x for x in tum_kalemler() if x["kaynak"] == "rg" and x.get("slug") == slug]
    print(f"\n── İlgili Resmî Gazete kayıtları ({slug})")
    if rgler:
        for x in rgler:
            print(f"   · {x['tarih']} · {x['baslik']}")
    else:
        print("   (yok — değişiklik RG'de yakalanmadı ya da tarama penceresinden önce)")
    return 0


# ─────────────────────────────────────────────────── detay: Resmî Gazete
RG_BELGE_DIR = os.path.join(KAYIT_DIR, "rg-belge")
PDF_MD = os.path.expanduser("~/Projects/_global-scripts/pdf-md/pdf-md.sh")


def _htm_metin(govde):
    kod = re.search(rb'charset=["\']?([\w-]+)', govde[:3000], re.I)
    for enc in ([kod.group(1).decode()] if kod else []) + ["utf-8", "windows-1254"]:
        try:
            t = govde.decode(enc)
            break
        except (LookupError, UnicodeDecodeError):
            continue
    else:
        t = govde.decode("utf-8", "replace")
    # RG sayfaları Word'den dışa aktarılmış HTML: <xml> ofis blokları ve
    # koşullu yorumlar metne "Print 120 Clean" gibi çöp basıyor; paragraf
    # içindeki satır sonları da kelimeleri bölüyor. Önce tüm boşluk tek boşluğa
    # iner, satır sonunu YALNIZ blok etiketleri üretir.
    t = re.sub(r"(?is)<!--.*?-->|<(script|style|xml|head)[^>]*>.*?</\1>", " ", t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"(?i)<br\s*/?>|</p>|</tr>|</div>|</h\d>|</li>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    t = "\n".join(" ".join(x.replace("\xa0", " ").split()) for x in t.split("\n"))
    return re.sub(r"\n{2,}", "\n", t).strip()


def _pdf_ocr(pdf):
    """Metin katmanı okunamayan PDF'i global `pdf-md.sh` ile BİR KEZ tarar,
    .md kopyasını döndürür (global kural: taranmış PDF bir kez taranır, sonra
    kopyadan okunur). Kopya kaynak md5'ini taşır; ikinci çağrı OCR yapmaz."""
    if not os.path.exists(PDF_MD):
        return ""
    hedef = os.path.join(RG_BELGE_DIR, "md")
    r = subprocess.run(["bash", PDF_MD, "--hedef", hedef, pdf],
                       capture_output=True, text=True, timeout=900)
    ad = os.path.splitext(os.path.basename(pdf))[0] + ".md"
    for yol in glob.glob(os.path.join(hedef, "**", ad), recursive=True):
        with open(yol, encoding="utf-8") as f:
            # kopyanın künye satırları (#, >, ```) atılır; "## Sayfa N" kalır
            return "\n".join(x for x in f.read().splitlines()
                             if not x.startswith(("# ", "> ", "```"))).strip()
    raise RuntimeError(f"pdf-md.sh kopya üretmedi: {(r.stderr or r.stdout).strip()[-200:]}")


def rg_belge_metni(url):
    """RG belgesini metne çevirir -> (metin, yöntem).
    .htm → etiketsiz metin · .pdf → pdftotext -layout · metin katmanı boşsa OCR.

    Sonuç kayit/rg-belge/ altında önbelleğe alınır (git dışı): RG'de yayımlanmış
    belge bir daha değişmez, ikinci detay isteği sunucuya hiç gitmez.

    ÖLÇÜLDÜ (25.09.2026): AYM kararları QuarkXPress PDF'i ve fontlarında Unicode
    eşlemesi YOK (`pdffonts`: uni=no) — pdftotext yalnız boşluk döndürüyor.
    Bu yüzden OCR yolu şart.

    TLS: www.resmigazete.gov.tr mevzuat.gov.tr ile AYNI sertifikayı (*.tccb.gov.tr)
    kullanıyor ve aynı eksik zinciri gönderiyor ("Verify return code: 21").
    Sistem deposuyla CERTIFICATE_VERIFY_FAILED verir; çözüm `-k` değil,
    sertifika/kur.sh'in bundle'ı (c.baglam()). api.resmigazete.gov.tr zinciri
    tam gönderdiği için rg.py'de bu gerekmiyor."""
    os.makedirs(RG_BELGE_DIR, exist_ok=True)
    ad = re.sub(r"[^\w.-]", "_", url.rstrip("/").rsplit("/", 1)[-1])
    onbellek = os.path.join(RG_BELGE_DIR, os.path.splitext(ad)[0] + ".txt")
    if os.path.exists(onbellek):
        with open(onbellek, encoding="utf-8") as f:
            ilk, _, metin = f.read().partition("\n")
        return metin, ilk.removeprefix("yöntem: ") + " (önbellek)"

    istek = urllib.request.Request(url, headers={"User-Agent": c.UA})
    with urllib.request.urlopen(istek, timeout=60, context=c.baglam()) as y:
        govde = y.read()
    if govde[:5] == b"%PDF-":
        pdf = os.path.join(RG_BELGE_DIR, os.path.splitext(ad)[0] + ".pdf")
        with open(pdf, "wb") as f:
            f.write(govde)
        metin, sayfa = c.pdf_metin(pdf)
        yontem = "pdftotext -layout"
        # HARF sayılır, boşluk-dışı karakter değil: eşlemesiz fontta pdftotext
        # glif kimliklerini kontrol baytı olarak basıyor (\x01-\x17) ve
        # "boş değil" görünüyor — 21.09.2026 kararlarının biri bu yüzden kaçtı.
        # Eşik SAYFA BAŞINADIR: 20260917-13 (15 sayfa) yalnız sayfa üst/alt
        # bilgisini ("Yönetmelik Adı – 3") metin olarak veriyor, 219 harf —
        # sabit 200 eşiğini geçip gövdesiz kalıyordu. Gerçek sayfa ~2.000 harf.
        if len(re.findall(r"[^\W\d_]", metin or "")) < 400 * max(sayfa or 1, 1):
            metin, yontem = _pdf_ocr(pdf), "OCR (pdf-md.sh) — sayı ve adları kaynakla karşılaştır"
    else:
        metin, yontem = _htm_metin(govde), "htm"
    if metin and metin.strip():
        with open(onbellek, "w", encoding="utf-8") as f:
            f.write(f"yöntem: {yontem}\n{metin}")
    return metin or "", yontem


HUKUM = re.compile(r"(?m)^\s*(?:[IVX]+\s*[.-]\s*)?HÜKÜM\s*$")


def _rg_detayi(no, k, tam):
    import rg as rgm
    _baslik_yaz(no, k, "Resmî Gazete kaydı")
    tarih = k["rg_tarih"]
    izlenen = _kaynak().get("mevzuat", [])
    sayi, kayitlar, hata = rgm.fihrist(tarih)
    print(f"Resmî Gazete : {k['tarih']}" + (f" · sayı {sayi}" if sayi else ""))
    if hata:
        print(f"⚠ Fihrist alınamadı: {hata}\nBildiğimiz: {k['baslik']} → {k['ozet']}")
        return 2

    for a in k["anahtarlar"]:
        baslik = a.partition("|")[2]
        rec = next((r for r in kayitlar if r["baslik"][:120] == baslik), None)
        print()
        if not rec:
            print(f"■ {baslik}\n  ⚠ Bu başlık o günün fihristinde bulunamadı.")
            continue
        s = rgm.suz([rec], izlenen)
        print(f"■ {rec['baslik']}")
        print(f"  Bölüm/kategori : {rec['bolum']} / {rec['kategori'] or '—'}")
        if s:
            print(f"  Neden yakalandı: {' · '.join(s[0]['sebep'])} ({s[0]['siddet']})")
        print(f"  Belge          : {rec['url']}")
        try:
            metin, yontem = rg_belge_metni(rec["url"]) if rec["url"] else ("", "")
        except Exception as e:
            print(f"  ⚠ Belge okunamadı: {type(e).__name__}: {e}")
            continue
        print(f"  Metin yöntemi  : {yontem}")
        if not metin:
            print("  ⚠ Belgeden metin çıkmadı.")
            continue
        aym = "anayasa mahkemesi" in c.tr_kucult(rec["baslik"] + " " + rec["kategori"])
        hk = list(HUKUM.finditer(metin))
        if tam:
            print(f"\n── RG METNİ (tam)\n{metin}")
        elif aym and hk:
            print(f"\n── RG METNİ · giriş\n{metin[:2500]}")
            print(f"\n── RG METNİ · HÜKÜM\n{metin[hk[-1].start():][:3000]}")
        else:
            print(f"\n── RG METNİ · ilk 6000 karakter (tamamı: --tam)\n{metin[:6000]}")
            if len(metin) > 6000:
                print(f"… {len(metin) - 6000} karakter daha")

    if k.get("slug"):
        d = c.yukle(motor.DURUM).get(k["slug"], {})
        sonra = [x for x in c.yukle(motor.GUNLUK, {"olaylar": []})["olaylar"]
                 if x.get("slug") == k["slug"] and x.get("zaman", "") >= tarih]
        print(f"\n── Konsolide metin durumu · {k['slug']}")
        print(f"   son doğrulama {d.get('son_dogrulama', '?')} · "
              f"son değişiklik {d.get('son_degisiklik', '?')}")
        if sonra:
            print("   mevzuat.gov.tr metnine İŞLENDİ — ilgili madde olayları:")
            for x in sonra:
                print(f"   · {x['id']} · {x.get('ozet', '')}")
        else:
            print("   mevzuat.gov.tr metnine HENÜZ İŞLENMEDİ (konsolidasyon gün(ler) "
                  "sürer). Günlük denetim işlendiği gün madde olayı üretecek.")
    return 0


GRUP_ADI = {"yeni": "A · son rapordan sonra", "onceki": "B · daha önce",
            "aym-yeni": "C · AYM, son rapordan sonra", "aym-onceki": "D · AYM, daha önce"}


def komut_detay(no, tam=False):
    durum = c.yukle(RAPOR_DURUM, {})
    liste = durum.get("liste") or []
    if not liste:
        print("Henüz rapor alınmamış — önce: python3 mevzuat.py degisiklikler")
        return 2
    kayit = next((x for x in liste if x["no"] == no), None)
    if not kayit:
        print(f"#{no} son listede yok. Son liste "
              f"({datetime.fromisoformat(durum.get('liste_zamani') or durum['son_rapor']):%d.%m.%Y %H:%M}) "
              f"1–{len(liste)} arası numara içeriyor.")
        return 2
    k = next((x for x in tum_kalemler() if x["kimlik"] == kayit["kimlik"]), None)
    if not k:
        print(f"#{no} ({kayit['kimlik']}) artık kaynak kayıtlarda yok "
              f"(gunluk.json / rg-gorulen.json budanmış olabilir).")
        return 2
    print(f"(Numara {datetime.fromisoformat(durum.get('liste_zamani') or durum['son_rapor']):%d.%m.%Y %H:%M} "
          f"tarihli listeye göre · {GRUP_ADI.get(kayit['grup'], kayit['grup'])})")
    return (_rg_detayi if k["kaynak"] == "rg" else _olay_detayi)(no, k, tam)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0].isdigit():
        sys.exit(komut_detay(int(a[0]), "--tam" in a))
    sys.exit(komut_liste("--kuru" in a))
