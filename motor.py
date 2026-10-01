#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
motor.py — denetim çekirdeği: çek · karşılaştır · olay üret

Tespit HİBRİTTİR (Ö-8) — 19.09.2026'da ölçülerek karara bağlandı:

  Kanun/KHK (statik dosya, 21 kayıt)
      İki indirme BAYT AYNI (sha cd75c7fe… = cd75c7fe…), ETag ve Last-Modified
      VAR → koşullu GET (If-None-Match) HTTP 304 döndürüyor.
      Tespit PDF baytından yapılır; pdftotext zincirden tamamen çıkar,
      değişmemiş belge hiç indirilmez.

  Yönetmelik/Tebliğ (GeneratePdf ile anlık üretilen, 24 kayıt)
      Aynı içerik iki indirmede FARKLI bayt (bd139070… ≠ d5c97c46…), ETag YOK.
      Bayt hash'i burada işe yaramaz → normalize METİN hash'i kullanılır.
"""
import difflib
import os
import shutil
from datetime import datetime

import analiz
import cekirdek as c

KOK = c.KOK
KAYNAK = os.path.join(KOK, "kaynak.json")
DURUM = os.path.join(KOK, "durum.json")
GUNLUK = os.path.join(KOK, "gunluk.json")
PDF_DIR = os.path.join(KOK, "pdf")
MET_DIR = os.path.join(KOK, "metin")
ARS_DIR = os.path.join(KOK, "arsiv")

# ── Ö-9: kütle-değişim devre kesici ─────────────────────────────────────────
# pdftotext çıktısı AYNI sürümde deterministik, SÜRÜMLER ARASINDA değil.
# poppler 0.88'de whitespace davranışı değişince R pdftools kullanıcılarının
# BÜTÜN çıktıları kaymıştı. Bizde bu "45 mevzuatın hepsi bugün değişti"
# alarmı demektir. Gerçek mevzuat değişikliği hiçbir zaman külliyatın beşte
# birini aynı gün değiştirmez.
DEVRE_KESICI_ORAN = 0.20
DEVRE_KESICI_ASGARI = 5      # 3 kayıtlık denemede oran anlamsız olur


def artiklari_temizle():
    """Yarıda kesilmiş koşudan kalan *.yeni.pdf dosyalarını siler.
    19.09.2026: ilk tam indirme 42/45'te kesildi ve 42 artık dosya bıraktı."""
    n = 0
    for ad in os.listdir(PDF_DIR):
        if ad.endswith(".yeni.pdf"):
            os.remove(os.path.join(PDF_DIR, ad))
            n += 1
    return n


def _slug_yollari(slug):
    return (os.path.join(PDF_DIR, slug + ".pdf"),
            os.path.join(MET_DIR, slug + ".txt"))


def cek(m, eski):
    """Bir mevzuatı çeker.
    -> dict(sonuc=..., ...) · sonuc: 'ok' | 'degismemis' | 'hata'

    'hata' hiçbir dosyayı DEĞİŞTİRMEZ ve asla 'değişti' sayılmaz:
    ölçüldü ki sunucu yığın istekte HTTP 200 ile HTML hata sayfası döndürüyor.
    """
    statik = c.statik_mi(m)

    # Koşullu GET yalnız statikte anlamlı (yönetmelik ETag vermiyor).
    ek = {}
    if statik and eski.get("etag"):
        ek["If-None-Match"] = eski["etag"]

    son_hata = ""
    for url in c.adresler(m):
        govde, baslik, kod = c.getir(url, ek_baslik=ek)

        if kod == 304:
            return {"sonuc": "degismemis", "url": url,
                    "etag": eski.get("etag", ""),
                    "son_degistirilme": eski.get("son_degistirilme", "")}

        if govde is None:
            son_hata = f"HTTP {kod or '000'}"
            ek = {}                      # sonraki adayda koşullu GET deneme
            continue

        # HTTP 200 başarı anlamına GELMEZ — sihirli bayt kontrolü şart.
        if govde[:5] != b"%PDF-":
            son_hata = "PDF değil (hata/kısıtlama sayfası döndü)"
            ek = {}
            continue

        gecici = os.path.join(PDF_DIR, m["slug"] + ".yeni.pdf")
        with open(gecici, "wb") as f:
            f.write(govde)
        metin, sayfa = c.pdf_metin(gecici)
        if not metin or len(metin) < 400:
            os.remove(gecici)
            son_hata = "metin çıkarılamadı / boş"
            ek = {}
            continue
        # YANLIŞ BELGE KORUMASI: adres kalıbı birden çok aday deniyor; yanlış
        # numara/tertip başka bir mevzuatın PDF'ini getirebilir ve sistem onu
        # sessizce "bu belge değişti" diye raporlar. `anahtar` tanımlıysa
        # belgenin BAŞINDA geçmesi beklenir.
        anahtar = m.get("anahtar")
        if anahtar and c.tr_kucult(anahtar) not in c.tr_kucult(metin[:4000]):
            os.remove(gecici)
            son_hata = f"içerik doğrulaması başarısız — '{anahtar}' belgenin başında yok"
            ek = {}
            continue
        return {"sonuc": "ok", "url": url, "gecici": gecici, "metin": metin,
                "sayfa": sayfa, "bayt_sha": c.sha(govde), "bayt": len(govde),
                "etag": (baslik.get("ETag") or "").strip(),
                "son_degistirilme": (baslik.get("Last-Modified") or "").strip()}

    # Son çare: fihrist iframe'i. y-yangin için TEK çalışan yol (GeneratePdf
    # orada HTTP 600 veriyor); ölçüm: 300.094 karakter, 181 madde.
    if m.get("iframe"):
        metin = c.iframe_metin(m["iframe"])
        if metin and len(metin) > 400:
            return {"sonuc": "ok", "url": m["iframe"], "gecici": None,
                    "metin": metin, "sayfa": 0, "bayt_sha": "", "bayt": 0,
                    "etag": "", "son_degistirilme": "", "kaynak": "iframe"}
        son_hata += " · iframe de başarısız"

    return {"sonuc": "hata", "not": son_hata or "adres çözülemedi"}


def kalem(m, durum, kuru=False):
    """Tek mevzuatı işler -> sonuç sözlüğü (olaylar dahil, henüz yazılmaz).

    `durum`a DOKUNMAZ. "ayni" sonucunun damgası (`dogrulama_zamani`) sonuçta
    taşınır; `durum`a ancak devre kesici geçtikten sonra `dogrulamayi_isle()`
    basar."""
    slug = m["slug"]
    eski = durum.get(slug, {})
    r = cek(m, eski)
    dogrulama_zamani = datetime.now().strftime("%d.%m.%Y %H:%M")
    son = {"slug": slug, "ad": m["ad"], "sinif": m["sinif"],
           "grup": m.get("grup", []), "olaylar": []}

    if r["sonuc"] == "hata":
        son.update(sonuc="hata", not_=r["not"])
        return son

    if r["sonuc"] == "degismemis":
        # Koşullu GET 304 verdi: sunucu "dosya hiç değişmedi" diyor.
        son.update(sonuc="ayni", yol="304", dogrulama_zamani=dogrulama_zamani)
        return son

    metin, pdf_yolu, met_yolu = r["metin"], *_slug_yollari(slug)
    metin_sha = c.sha(metin)
    statik = c.statik_mi(m)

    # Hangi imza tespit için esas alınacak (Ö-8)
    imza = r["bayt_sha"] if (statik and r["bayt_sha"]) else metin_sha
    eski_imza = eski.get("imza", "")

    ilk = not eski_imza
    degisti = (not ilk) and eski_imza != imza

    # Sessiz kısalma koruması: içerik yarıdan fazla küçüldüyse bu değişiklik
    # değil bozuk indirmedir. Depodaki nüshaya DOKUNULMAZ.
    if eski.get("karakter") and len(metin) < eski["karakter"] * 0.5:
        if r.get("gecici"):
            os.remove(r["gecici"])
        son.update(sonuc="hata",
                   not_=f"metin %{100 - round(len(metin) / eski['karakter'] * 100)} "
                        f"kısaldı ({eski['karakter']}→{len(metin)}) — indirme bozuk "
                        f"sayıldı, dosyalara dokunulmadı")
        return son

    # Madde envanteri (Ö-10: dipnotlar gövdeden ayrılmış hâlde)
    yeni_env, mukerrer = analiz.envanter(metin)
    eski_env = eski.get("envanter") or {}

    if degisti and eski_env:
        son["olaylar"] = analiz.karsilastir(eski_env, yeni_env,
                                            m.get("kritik_madde", []))
    # Ö-4: belirsizlik sessizce yutulmasın
    if mukerrer:
        son["mukerrer"] = sorted(set(mukerrer))

    son.update(sonuc="ilk" if ilk else ("degisti" if degisti else "ayni"),
               sayfa=r["sayfa"], karakter=len(metin), madde=len(yeni_env),
               eski_imza=eski_imza, yeni_imza=imza,
               metin_sha=metin_sha, yol=r.get("kaynak", "pdf"),
               envanter=yeni_env, metin=metin, gecici=r.get("gecici"),
               etag=r["etag"], son_degistirilme=r["son_degistirilme"],
               url=r["url"], dogrulama_zamani=dogrulama_zamani)
    # Geçici dosya YALNIZ yazılacaksa saklanır. "ayni" sonucunda motor.yaz()
    # çağrılmaz; temizlenmezse her denetimde bir artık dosya birikir
    # (19.09.2026: ilk iki koşudan 24 artık .yeni.pdf kaldı).
    if r.get("gecici") and (kuru or son["sonuc"] == "ayni"):
        os.remove(r["gecici"])
        son["gecici"] = None
    return son


def yaz(m, s, durum):
    """Kalem sonucunu diske işler. Devre kesici tetiklendiyse ÇAĞRILMAZ."""
    slug = m["slug"]
    eski = durum.get(slug, {})
    pdf_yolu, met_yolu = _slug_yollari(slug)
    damga = datetime.now().strftime("%Y-%m-%d")

    if s["sonuc"] == "degisti" and os.path.exists(met_yolu):
        kisa = (eski.get("metin_sha") or "")[:8]
        shutil.copy2(met_yolu, os.path.join(ARS_DIR, f"{slug}_{damga}_{kisa}.txt"))
        with open(met_yolu, encoding="utf-8") as f:
            onceki = f.read()
        fark = "".join(difflib.unified_diff(
            onceki.splitlines(keepends=True), s["metin"].splitlines(keepends=True),
            fromfile=f"{slug} (eski {kisa})", tofile=f"{slug} (yeni {s['metin_sha'][:8]})",
            n=3))
        fk = os.path.join(ARS_DIR, f"{slug}_{damga}_fark.diff")
        with open(fk, "w", encoding="utf-8") as f:
            f.write(fark)
        s["fark_dosyasi"] = os.path.relpath(fk, KOK)
        s["fark_satir"] = sum(1 for l in fark.splitlines()
                              if l[:1] in "+-" and l[:3] not in ("+++", "---"))

    if s.get("gecici"):
        shutil.move(s["gecici"], pdf_yolu)
    with open(met_yolu, "w", encoding="utf-8") as f:
        f.write(s["metin"])

    durum[slug] = {
        "ad": m["ad"], "no": m["no"], "tur": m["tur"], "tertip": m["tertip"],
        "sinif": m["sinif"], "grup": m.get("grup", []),
        "url": s["url"], "sayfa_url": c.sayfa_url(m),
        "imza": s["yeni_imza"], "imza_turu": "bayt" if c.statik_mi(m) else "metin",
        "metin_sha": s["metin_sha"], "etag": s["etag"],
        "son_degistirilme": s["son_degistirilme"],
        "sayfa": s["sayfa"], "karakter": s["karakter"], "madde": s["madde"],
        "yol": s["yol"], "mukerrer": s.get("mukerrer", []),
        "envanter": s["envanter"],
        "madde_ozeti": analiz.ozet_sayim(s["envanter"]),
        # Ö-9: hangi araç sürümüyle üretildi
        "arac_surumu": c.poppler_surumu(),
        "ilk_indirme": eski.get("ilk_indirme", datetime.now().strftime("%d.%m.%Y")),
        "son_dogrulama": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "son_degisiklik": (datetime.now().strftime("%d.%m.%Y")
                           if s["sonuc"] == "degisti"
                           else eski.get("son_degisiklik", "—")),
    }


def dogrulamayi_isle(durum, sonuclar):
    """Değişmemiş ("ayni") kayıtların `son_dogrulama` damgasını basar -> kaç kayıt.

    Değişmemiş kayıt `yaz()`dan geçmez; damgası yalnız buradan basılır.
    Yalnız kuru olmayan koşuda ve devre kesici GEÇTİKTEN sonra çağrılır:
    kesici tetiklendiyse koşunun ölçümüne güvenilmez, 304 dahil hiçbir kayıt
    "doğrulandı" sayılmaz.

    25.09.2026'da bulunan hata: damga yalnız 304 dalında basılıyordu. Kanun/KHK
    koşullu GET ile 304 aldığı için damgalanıyor, GeneratePdf ile üretilen
    yönetmelikler ("metin" imzalı) metin hash'iyle "ayni" çıkınca hiçbir yere
    yazılmıyordu — 27 yönetmelik her gün denetlendiği hâlde `son_dogrulama`
    19.09'da donmuştu. Altın kural alıntıdan önce bu damgaya baktığı için
    sessiz ama ciddi bir hataydı."""
    n = 0
    for r in sonuclar:
        if r["sonuc"] == "ayni" and r["slug"] in durum and r.get("dogrulama_zamani"):
            durum[r["slug"]]["son_dogrulama"] = r["dogrulama_zamani"]
            n += 1
    return n


def devre_kesici(sonuclar):
    """Ö-9 -> (tetiklendi_mi, mesaj)"""
    islenen = [r for r in sonuclar if r["sonuc"] in ("degisti", "ayni")]
    degisen = [r for r in sonuclar if r["sonuc"] == "degisti"]
    if len(islenen) < DEVRE_KESICI_ASGARI:
        return False, ""
    oran = len(degisen) / len(islenen)
    if oran < DEVRE_KESICI_ORAN:
        return False, ""
    surumler = {r.get("arac_surumu") for r in sonuclar if r.get("arac_surumu")}
    return True, (
        f"Külliyatın %{round(oran * 100)}'i ({len(degisen)}/{len(islenen)}) aynı koşuda "
        f"'değişti' göründü. Gerçek mevzuat değişikliği böyle davranmaz.\n"
        f"    Muhtemel sebep: pdftotext sürüm değişikliği (şu an {c.poppler_surumu()}) "
        f"ya da normalizasyon değişikliği.\n"
        f"    Hiçbir dosya güncellenmedi, bildirim gönderilmedi.\n"
        f"    Yapılacak: `python3 mevzuat.py denetle --kuru` ile farkları incele; "
        f"araç değiştiyse `--devre-kesiciyi-atla` ile yeniden temel al.")


def gunluge_yaz(kayitlar):
    """Olayları gunluk.json'a ekler (arayüz bunu okur)."""
    g = c.yukle(GUNLUK, {"olaylar": []})
    simdi = datetime.now()
    sira = len(g["olaylar"])
    for k in kayitlar:
        sira += 1
        k["id"] = f"O-{simdi:%Y%m%d}-{sira:04d}"
        k["zaman"] = simdi.isoformat(timespec="seconds")
        k["tarih"] = simdi.strftime("%d.%m.%Y %H:%M")
        k.setdefault("okundu", False)
        k.setdefault("not", "")
        g["olaylar"].append(k)
    c.kaydet(GUNLUK, g)
    return g
