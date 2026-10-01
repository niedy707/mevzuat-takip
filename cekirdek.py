#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cekirdek.py — indirme katmanı: doğrulanmış TLS · hibrit tespit · nezaket

Neden ayrı dosya: `mevzuat.py` komutları, `sunucu.py` arayüzü ve `rg.py` ikinci
sinyali aynı indirme mantığını paylaşır. Üç kopya olmasın diye burada toplandı
(ekosistemde zaten üç ayrı mevzuat motoru var — bkz. mevzuat_tara.md Ö-11).
"""
import hashlib
import json
import os
import re
import ssl
import subprocess
import time
import unicodedata
import urllib.error
import urllib.request

KOK = os.path.dirname(os.path.abspath(__file__))
CA = os.path.join(KOK, "sertifika", "mevzuat-ca.pem")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# ── TLS (Ö-13) ──────────────────────────────────────────────────────────────
# www.mevzuat.gov.tr zincirde yalnız leaf sertifikayı gönderiyor; tarayıcı eksik
# ara sertifikayı AIA'dan kendi çeker, OpenSSL çekmez. Çözüm `-k` DEĞİL,
# sertifika/kur.sh'in ürettiği bundle'dır.
#
# ÖLÇÜLDÜ (19.09.2026) — bu yüzden curl değil urllib kullanılıyor:
#   Apple curl (SecureTransport): DOĞRU ve YANLIŞ CA ile de exit=0.
#       macOS güven değerlendirmesi araya giriyor; --cacert gerçek güvence vermiyor.
#   Python ssl (OpenSSL):  doğru CA ✅ · yanlış CA ❌ · varsayılan ❌
#       Gerçek doğrulama burada. İşi resmî metnin doğruluğunu garanti etmek olan
#       bir araçta doğrulamanın ölçülebilir olması şart.
_baglam = None
_tls_uyarisi = ""


def baglam():
    """Doğrulayan SSL bağlamı. Bundle yoksa doğrulamasız bağlama DÜŞMEZ —
    çağıran `tls_uyarisi()` ile durumu görür ve kullanıcıya söyler."""
    global _baglam, _tls_uyarisi
    if _baglam is None:
        if os.path.exists(CA):
            _baglam = ssl.create_default_context(cafile=CA)
        else:
            _baglam = ssl.create_default_context()
            _baglam.check_hostname = False
            _baglam.verify_mode = ssl.CERT_NONE
            _tls_uyarisi = ("sertifika/mevzuat-ca.pem yok — TLS DOĞRULAMASI KAPALI. "
                            "Düzeltmek için: bash sertifika/kur.sh")
    return _baglam


def tls_uyarisi():
    baglam()
    return _tls_uyarisi


# ── Nezaket ve yeniden deneme ───────────────────────────────────────────────
# ÖLÇÜLDÜ (19.09.2026): 11 adresi 2 sn aralıkla arka arkaya çekince sunucu
# kısıtlamaya girdi ve HTTP 200 ile HTML hata sayfası döndürdü — PDF değil.
# Aynı adres 3 sn aralıkla 5/5 başarılı oldu. Yani:
#   · tek başarısızlık "ulaşılamadı" DEĞİL, "yavaşla" demektir
#   · HTTP 200 başarı anlamına GELMEZ; '%PDF-' sihirli baytı kontrol edilmelidir
NEZAKET = 1.5
GERI_CEKILME = (6, 18, 45)
_son_istek = [0.0]


def _bekle():
    gecen = time.monotonic() - _son_istek[0]
    if gecen < NEZAKET:
        time.sleep(NEZAKET - gecen)
    _son_istek[0] = time.monotonic()


def getir(url, ek_baslik=None, sure=90, deneme=3):
    """-> (govde_baytlari, basliklar, http_kodu)
       304  -> (None, basliklar, 304)   değişmemiş (koşullu GET)
       hata -> (None, {}, kod)"""
    son_kod = 0
    for i in range(deneme):
        _bekle()
        istek = urllib.request.Request(
            url, headers={"User-Agent": UA, **(ek_baslik or {})})
        try:
            with urllib.request.urlopen(istek, timeout=sure, context=baglam()) as y:
                return y.read(), dict(y.headers), y.status
        except urllib.error.HTTPError as e:
            son_kod = e.code
            if e.code == 304:                 # değişmemiş — hata değil
                return None, dict(e.headers), 304
            if e.code in (400, 403, 404, 410):   # kalıcı: yeniden deneme boşuna
                return None, {}, e.code
        except Exception:
            son_kod = son_kod or 0
        if i < deneme - 1:
            time.sleep(GERI_CEKILME[i])
    return None, {}, son_kod


# ── Adres üretimi ───────────────────────────────────────────────────────────
M = "https://www.mevzuat.gov.tr/MevzuatMetin/"
G = "https://www.mevzuat.gov.tr/File/GeneratePdf"


def statik_mi(m):
    """Kanun ve KHK statik dosyadır: bayt-kararlı, ETag verir → koşullu GET
    mümkün. Yönetmelik GeneratePdf ile ANLIK üretilir: aynı içerik her
    indirmede farklı bayt, ETag yok. (19.09.2026'da ikisi de ölçüldü.)"""
    return m["tur"] in ("Kanun", "KHK")


def adresler(m):
    """Denenecek adresler, sırayla."""
    a = list(m.get("url_adaylari") or [])
    t, tp, no = m["tur_no"], m["tertip"], m["no"]
    if statik_mi(m):
        a.append(f"{M}{t}.{tp}.{no}.pdf")
    else:
        a.append(f"{G}?mevzuatNo={no}&mevzuatTur={m['tur']}&mevzuatTertip={tp}")
        a.append(f"{M}yonetmelik/{t}.{tp}.{no}.pdf")
        a.append(f"{M}{t}.{tp}.{no}.pdf")
    return a


def sayfa_url(m):
    return (f"https://www.mevzuat.gov.tr/mevzuat?MevzuatNo={m['no']}"
            f"&MevzuatTur={m['tur_no']}&MevzuatTertip={m['tertip']}")


# ── Metin çıkarımı ──────────────────────────────────────────────────────────
_poppler = None


def poppler_surumu():
    """Ö-9: sürüm damgası. pdftotext çıktısı AYNI sürümde deterministik,
    SÜRÜMLER ARASINDA değildir (poppler changelog'unda çıkarımı değiştiren çok
    sayıda kayıt var; 0.88'de whitespace davranışı değişince R pdftools
    kullanıcılarının bütün çıktıları kaymıştı). Hash farkı görüldüğünde önce
    bu damga karşılaştırılır: sürüm değiştiyse 'mevzuat değişti' değil
    'araç değişti' sonucu çıkarılır."""
    global _poppler
    if _poppler is None:
        try:
            r = subprocess.run(["pdftotext", "-v"], capture_output=True, text=True)
            b = re.search(r"version\s+([\d.]+)", r.stderr + r.stdout)
            _poppler = b.group(1) if b else "bilinmiyor"
        except Exception:
            _poppler = "yok"
    return _poppler


def normalize(metin):
    """Hash'in kararlı olması için. NFKC ligatür (ﬁ→fi) ve üst simgeyi (²→2)
    çözer, Türkçe İ/ı'yı bozmaz (denendi)."""
    metin = unicodedata.normalize("NFKC", metin)
    metin = metin.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    satir = [s.rstrip() for s in metin.split("\n")]
    cikti, bos = [], 0
    for s in satir:
        if s:
            bos = 0
            cikti.append(s)
        else:
            bos += 1
            if bos <= 1:
                cikti.append("")
    return "\n".join(cikti).strip() + "\n"


def pdf_metin(pdf_yolu):
    """-> (normalize metin, sayfa sayısı) · başarısızsa (None, 0)
    `-layout` KORUNUR: resmî man sayfası `-raw` için 'no longer recommended'
    diyor ve varsayılan mod kanun künye tablosunda etiket–değer eşleşmesini
    bozuyor (ölçüldü) — 'Kanun Numarası : 634' yerine önce tüm etiketler,
    sonra tüm değerler geliyor."""
    cikti = pdf_yolu + ".cikti.txt"
    subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", pdf_yolu, cikti],
                   capture_output=True)
    if not os.path.exists(cikti):
        return None, 0
    with open(cikti, encoding="utf-8", errors="replace") as f:
        ham = f.read()
    os.remove(cikti)
    return normalize(ham), ham.count("\f") + 1


def iframe_metin(url):
    """Son çare: fihrist iframe'i belgenin tam metnini sunucu tarafında render
    eder. y-yangin (Binaların Yangından Korunması) için TEK çalışan yol —
    GeneratePdf orada HTTP 600 döndürüyor. Ölçüm: 300.094 karakter, 181 madde."""
    govde, _, kod = getir(url, sure=120)
    if not govde or kod != 200:
        return None
    ham = govde.decode("utf-8", errors="replace")
    if len(ham) < 40000:           # kabuk sayfa — belge içermiyor
        return None
    ham = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", ham, flags=re.S | re.I)
    ham = re.sub(r"<br[^>]*>", "\n", ham, flags=re.I)
    ham = re.sub(r"</(p|div|tr|h[1-6]|li)>", "\n", ham, flags=re.I)
    ham = re.sub(r"<[^>]+>", " ", ham)
    import html as H
    ham = H.unescape(ham)
    return normalize("\n".join(re.sub(r"[ \t\xa0]+", " ", x).strip()
                               for x in ham.split("\n")))


def tr_kucult(s):
    """Türkçe küçültme. Python'un `str.lower()`/`re.IGNORECASE`'i I/ı/İ/i
    ayrımını Türkçe kurallarına göre yapmaz — IGNORECASE'te `ı` ile `i`
    birbiriyle eşleşir ve "tıp" deseni "Tip"i yakalar (19.09.2026'da ölçüldü)."""
    return s.replace("I", "ı").replace("İ", "i").lower()


def sha(x):
    return hashlib.sha256(x if isinstance(x, bytes) else x.encode("utf-8")).hexdigest()


def yukle(yol, varsayilan=None):
    if not os.path.exists(yol):
        return varsayilan if varsayilan is not None else {}
    with open(yol, encoding="utf-8") as f:
        return json.load(f)


KAYNAK_YOL = os.path.join(KOK, "kaynak.json")
NOTLAR_YOL = os.path.join(KOK, "kaynak-notlar.json")


def kaynak():
    """İzlenen mevzuat listesi — `kaynak-notlar.json` varsa birleştirilmiş hâli.

    GİZLİLİK AYRIMI (02.10.2026): bu depo PUBLIC'tir. `neden` alanları
    (bir mevzuatın hangi dosya/uyuşmazlık için izlendiği) ve `_atif_kokleri`
    (taranacak yerel proje yolları) kişiseldir; `kaynak-notlar.json` içinde
    tutulur ve git'e girmez.

    Notlar dosyası YOKSA araç tam çalışır — yalnız arayüzdeki "neden izleniyor"
    boş kalır ve `etki` komutu taranacak kök bulamadığını söyler. Yani depoyu
    klonlayan biri için hiçbir şey kırılmaz.
    """
    d = yukle(KAYNAK_YOL)
    n = yukle(NOTLAR_YOL, {})
    if not n:
        return d
    neden = n.get("neden") or {}
    for m in d.get("mevzuat", []):
        if m.get("slug") in neden:
            m["neden"] = neden[m["slug"]]
    if n.get("_atif_kokleri"):
        d["_atif_kokleri"] = n["_atif_kokleri"]
    return d


def kaydet(yol, veri):
    gecici = yol + ".yeni"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(gecici, yol)        # yarıda kesilirse dosya bozulmasın
