#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rg.py — Resmî Gazete günlük fihristi: İKİNCİ BAĞIMSIZ SİNYAL (Ö-1)

NEDEN VAR: mevzuat.gov.tr yalnız KONSOLİDE metni sunar ve konsolidasyon
RG yayımından gün(ler) sonra yapılır. Bir yönetmelik değişikliği Resmî
Gazete'de yayımlandığı GÜN buradan görülür; metin hash'i ise ancak
mevzuat.gov.tr metni güncelleyince değişir.

DOĞRULAMA (19.09.2026): 20.08–19.09.2026 arası 31 gün tarandı. Süzgeç
29.08.2026 tarihli "Özel Hastaneler Yönetmeliğinde Değişiklik Yapılmasına
Dair Yönetmelik" kaydını yakaladı — külliyattaki `GEÇİCİ MADDE 15-
(Ek:RG-29/8/2026-33355)` şerhinin kaynağı tam olarak bu.

API dokümante DEĞİLDİR (muhtemelen mobil uygulamanın ucu) → sözleşme
garantisi yok. Kırılırsa yedek: www.resmigazete.gov.tr ana sayfası günün
fihristini sunucu tarafında render ediyor (`fihrist-item` sınıfı).
RSS YOKTUR: /rss ana sayfaya düşüyor, /rss/rss.xml 404 (üçü de test edildi).
"""
import json
import re
import sys
import urllib.request
from datetime import date, timedelta

import cekirdek

API = "https://api.resmigazete.gov.tr/api/Catalog/GetCatalogs?date={}"


# ── Türkçe küçültme ─────────────────────────────────────────────────────────
# TUZAK (19.09.2026'da ölçüldü): Python'un `re.IGNORECASE`'i Unicode katlaması
# yaptığı için `ı` (U+0131) ile `i` ikisi de `I`'ya katlanır ve BİRBİRİYLE
# EŞLEŞİR. Sonuç: "tıp " deseni "Tip Onayı" ifadesini yakaladı ve motorlu
# araç tip onayı yönetmeliği "sağlık mevzuatı" sayıldı.
# Çözüm: IGNORECASE KULLANILMAZ. Metin Türkçe kurallarına göre küçültülür
# (I→ı, İ→i) ve desenler küçük harfle, büyük/küçük duyarlı eşleştirilir.
tr_kucult = cekirdek.tr_kucult


# ── Alan süzgeçleri ─────────────────────────────────────────────────────────
# Anahtarlar 31 günlük gerçek fihrist üzerinde kalibre edildi.
SAGLIK = re.compile(
    r"sağlık|hasta|hastane|tıbb|tıp fakült|tıpta uzmanl|hekim|tabip|eczac|eczane"
    r"|ilaç|beşeri tıbbi|sosyal güvenlik kurumu|sağlık uygulama tebliğ|sut\b"
    r"|muayenehane|poliklinik|ameliyat|klinik|laboratuvar|tahlil|görüntüleme"
    r"|titck|türkiye ilaç|sağlık bakanlığı|hemşire|ebelik|sağlık meslek"
    r"|tıbbi cihaz|optisyen|gözlükçü|fizyoterap|psikolog|diyetisyen|aile hekim"
    r"|acil sağlık|ambulans|acil tıp|ağız ve diş|diş hekim|estetik|güzellik"
    r"|biyosidal|sağlık turizm|kozmetik|organ nakli|kan ve kan ürün"
    # "aşı" iki yanı da sınırlı olmalı: sınırsızken "gölbaşı ilçesi" kaydını
    # sağlık mevzuatı sandı (19.09.2026'da ölçüldü).
    r"|\başı\b|aşılama|bağışıklama")

# Üniversitelerin KENDİ iç yönetmelikleri (sınav, fakülte, araştırma merkezi)
# klinik uygulamayı ilgilendirmez — 31 günde 18 sağlık eşleşmesinin 8'i buydu.
# Veteriner de kapsam dışı (hayvan sağlığı).
GURULTU = re.compile(
    r"üniversitesi.{0,120}(eğitim-öğretim ve sınav|uygulama ve araştırma merkezi"
    r"|önlisans ve lisans|lisansüstü eğitim)"
    r"|rektörlüğü bünyesinde"                       # fakülte kurulması / ad değişikliği
    r"|fakültesi(nin)? (kurulması|adının|kapatılması)"
    r"|veteriner|hayvan sağlığı|gıda ve yem|su ürünleri"
    r"|kamulaştır|taşınmaz.{0,40}kamulaş")

# Elektrik abonelik rejimini yılda bir kez değiştiren EPDK Kurul Kararları
# mevzuat.gov.tr'de YAYIMLANMAZ — yalnız Resmî Gazete'de çıkarlar, yani madde
# envanteri motoru onları hiç göremez. Bu süzgeç o boşluğu kapatır (20.09.2026).
#
# ÖLÇÜLDÜ (20.09.2026, 180 gün · 2.079 fihrist kaydı): EPDK Kurul Kararı ayda
# ortalama 4,0 kez yayımlanıyor. VE BAŞLIK KONUYU HİÇ YAZMIYOR — fihristte
# yalnız "Enerji Piyasası Düzenleme Kurulunun 30/10/2025 Tarihli ve 13912
# Sayılı Kararı" yazıyor. Bu yüzden konu anahtarıyla ("son kaynak",
# "serbest tüketici", "tarife") süzmek İMKÂNSIZ; denendi, hiçbir gerçek kaydı
# yakalamadı. Tek çalışan yol kurumu yakalayıp kararı açmak.
#
# Kaçırılmaması gerekenler ve neden (hepsi bu biçimde yayımlandı):
#   · KK 13912 · RG 31.10.2025-33063 → mesken son kaynak eşiği 2026 için
#     4.000 kWh/yıl (2025'te 5.000'di). Eşiğin altındaki hane faturasının
#     ~%46'sını devlet desteği olarak alıyor; eşik aşılırsa destek biter.
#   · KK 14039 · RG 23.12.2025-33116 → 2026 serbest tüketici limiti 500 kWh
#     (2024: 950, 2025: 750). Tedarikçi değiştirme hakkının kapısı.
#   · KK 14461 · RG 04.04.2026-33214 → 04.04.2026'dan geçerli tarife tabloları.
#
# ŞİDDET "onemli"de BIRAKILIR, kritiğe yükseltilmez: başlık konuyu söylemediği
# için ayda 4 kez "kritik" demek kurt masalı olur. Eşik kararları Ekim-Aralık'ta
# çıkıyor (Yönetmelik m.41: serbest tüketici limiti her yılın 1 Ocak'ına kadar
# belirlenir, Ocak sonuna kadar RG'de yayımlanır) — o pencerede sebep metni
# kullanıcıyı kararı açmaya çağırır.
EPDK_KARAR = re.compile(r"enerji piyasası düzenleme kurulu")
# Eşik/limit kararlarının yayımlandığı pencere (ay numaraları).
ESIK_PENCERESI = (10, 11, 12, 1)

# "Yürütmenin durdurulması" RG'de de duyurulabilir — projenin ana derdi bu.
YD_IZ = re.compile(r"yürütme(?:si|sinin|nin)? durdur|yürütmenin durdurulması")

BOLUM_ILAN = re.compile(r"[iİ]l[aâà]n")


def _gun_getir(gun):
    istek = urllib.request.Request(API.format(gun),
                                   headers={"User-Agent": cekirdek.UA})
    with urllib.request.urlopen(istek, timeout=45) as y:
        return json.load(y)


def fihrist(gun):
    """Bir günün fihristini düz listeye açar.
    -> (sayi, [{bolum, kategori, baslik, url}], hata)

    İLÂN BÖLÜMÜ burada ELENMEZ, işaretlenir — eleme `suz()`'de yapılır ki
    sayım şeffaf kalsın. Alt kategori İLÂN bölümünde bir öncekinden devralınıyor
    (ölçüldü), bu yüzden eleme ÜST BÖLÜME göre yapılmalıdır."""
    try:
        d = _gun_getir(str(gun))
    except Exception as e:
        return None, [], f"{type(e).__name__}: {e}"
    kayitlar, ust, alt = [], "", ""
    for k in (d.get("catalogs") or []):
        for x in (k.get("items") or []):
            t, metin = x.get("type"), str(x.get("text") or "").strip()
            if t == 1:
                ust, alt = metin, ""
            elif t == 2:
                alt = metin
            elif t == 3:
                kayitlar.append({
                    "bolum": ust, "kategori": alt,
                    "baslik": metin.lstrip("–- ").strip(),
                    "url": x.get("url") or "",
                    "ilan": bool(BOLUM_ILAN.search(tr_kucult(ust))),
                })
    return d.get("resmiGazeteSayisi"), kayitlar, ""


def suz(kayitlar, izlenen=()):
    """Kayıtları ilgi sebebine göre etiketler.
    -> [{... , sebep: [...], siddet: "kritik"|"onemli"}]

    İlan bölümü tamamen elenir (kullanıcı kararı, 19.09.2026).
    """
    izlenen = list(izlenen)
    sonuc = []
    for k in kayitlar:
        if k["ilan"]:
            continue
        kb = tr_kucult(k["baslik"])
        kk = tr_kucult(k["kategori"])
        sebep, siddet = [], "onemli"

        # 1) İzlenen 45 belgeden biri mi? (en güçlü sinyal)
        for m in izlenen:
            ad = tr_kucult(m["ad"])
            cekirdek_ad = re.sub(r"\s*\(.*?\)\s*", " ", ad).strip()
            anahtar = m.get("rg_anahtar") or cekirdek_ad
            if anahtar and len(anahtar) > 8 and tr_kucult(anahtar) in kb:
                sebep.append(f"izlenen: {m['slug']}")
                siddet = "kritik"
                break
            if m["tur"] in ("Kanun", "KHK") and re.search(
                    rf"\b{m['no']}\b", k["baslik"]):
                sebep.append(f"izlenen: {m['slug']} (no)")
                siddet = "kritik"
                break

        # 2) Anayasa Mahkemesi kararı (kullanıcı açıkça istedi)
        if "anayasa mahkemesi" in kk or "anayasa mahkemesi" in kb:
            sebep.append("Anayasa Mahkemesi kararı")
            siddet = "kritik"

        # 3) Danıştay kararı — yürütme durdurma buradan da duyurulabilir
        if "danıştay" in kk or "danıştay" in kb:
            sebep.append("Danıştay kararı")
            siddet = "kritik"

        # 4) Yürütmenin durdurulması ibaresi
        if YD_IZ.search(kb):
            sebep.append("YÜRÜTMENİN DURDURULMASI")
            siddet = "kritik"

        # 5) EPDK Kurul Kararı — konu başlıkta YAZMAZ, kararın kendisi açılır
        if EPDK_KARAR.search(kb) or EPDK_KARAR.search(kk):
            if date.today().month in ESIK_PENCERESI:
                sebep.append("EPDK Kurul Kararı — EŞİK PENCERESİ: "
                             "son kaynak tüketim eşiği / serbest tüketici limiti olabilir, AÇ")
            else:
                sebep.append("EPDK Kurul Kararı — konusu başlıkta yazmaz, açılıp bakılır")

        # 6) Sağlık alanı (kullanıcı isteği) — üniversite iç mevzuatı hariç
        if SAGLIK.search(kb) and not GURULTU.search(kb):
            sebep.append("sağlık mevzuatı")

        if sebep:
            k = dict(k, sebep=sebep, siddet=siddet)
            sonuc.append(k)
    return sonuc


def tara(gun_sayisi=1, bitis=None, izlenen=()):
    """Son N günün fihristini tarar. -> (bulgular, hatalar, taranan_gun)"""
    bitis = bitis or date.today()
    bulgu, hata, tarandi = [], [], 0
    for i in range(gun_sayisi):
        g = bitis - timedelta(days=i)
        sayi, kayitlar, h = fihrist(g)
        if h:
            hata.append((str(g), h))
            continue
        tarandi += 1
        for k in suz(kayitlar, izlenen):
            k["tarih"] = str(g)
            k["rg_sayi"] = sayi
            bulgu.append(k)
    return bulgu, hata, tarandi


if __name__ == "__main__":
    import os
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 7
    kaynak = cekirdek.kaynak()
    b, h, t = tara(n, izlenen=kaynak.get("mevzuat", []))
    print(f"Resmî Gazete taraması · son {n} gün · {t} gün okundu · {len(b)} ilgili kayıt")
    for x in b:
        im = "🔴" if x["siddet"] == "kritik" else "🟡"
        print(f" {im} {x['tarih']} [{x['kategori'][:20]}] {x['baslik'][:78]}")
        print(f"      → {' · '.join(x['sebep'])}")
    for g, e in h:
        print(f" ✖ {g}: {e}")
