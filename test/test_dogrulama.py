# -*- coding: utf-8 -*-
"""`son_dogrulama` damgası testleri — denetim koşusunun durum.json'a ne yazdığı.

25.09.2026: GeneratePdf ile üretilen yönetmeliklerde (imza_turu "metin")
denetim her gün koştuğu hâlde `son_dogrulama` 19.09.2026'da kalmıştı. Damga
yalnız 304 dalında basılıyordu; metin hash'i "ayni" çıkan kayıt hiçbir yere
yazılmıyordu. `madde` çıktısındaki "son doğrulama" bu yüzden bayat görünüyor,
bir ay sonra her yönetmelik alıntısı gereksiz yere denetim isteyecekti.

Testler ağa çıkmaz: `motor.cek()` sahte sonuç döndürür, dosyalar geçici
dizine yazılır, `mevzuat._kos()` uçtan uca koşulur.
"""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cekirdek as c  # noqa: E402
import motor  # noqa: E402
import mevzuat  # noqa: E402

ESKI = "19.09.2026 22:35"
BICIM = re.compile(r"^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$")

METIN_AYNI = "MADDE 1 – (1) Birinci hüküm.\nMADDE 2 – (1) İkinci hüküm.\n"
METIN_YENI = "MADDE 1 – (1) Birinci hüküm, değiştirildi.\nMADDE 2 – (1) İkinci.\n"


def _kayit(slug, tur="KurumVeKurulusYonetmeligi"):
    return {"slug": slug, "ad": slug, "sinif": "test", "grup": [],
            "no": "1", "tur": tur, "tur_no": 7, "tertip": 5}


def _ok(metin):
    """GeneratePdf yolunun başarılı indirmesi (bayt hash'i yok, geçici dosya yok)."""
    return {"sonuc": "ok", "url": "https://ornek/", "gecici": None, "metin": metin,
            "sayfa": 1, "bayt_sha": "", "bayt": 0, "etag": "", "son_degistirilme": ""}


class SonDogrulamaDamgasi(unittest.TestCase):

    def setUp(self):
        self.kok = tempfile.mkdtemp(prefix="mevzuat-test-")
        yollar = {"DURUM": "durum.json", "GUNLUK": "gunluk.json",
                  "PDF_DIR": "pdf", "MET_DIR": "metin", "ARS_DIR": "arsiv"}
        for ad, alt in yollar.items():
            yol = os.path.join(self.kok, alt)
            if ad.endswith("_DIR"):
                os.makedirs(yol)
            p = mock.patch.object(motor, ad, yol)
            p.start()
            self.addCleanup(p.stop)
        for ad, donus in (("tls_uyarisi", ""), ("poppler_surumu", "test")):
            p = mock.patch.object(c, ad, return_value=donus)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.kok, ignore_errors=True)

    def _kur(self, kayitlar, durum, cevaplar):
        """kaynak + durum.json + her slug için sahte cek() cevabı."""
        c.kaydet(motor.DURUM, durum)
        p = mock.patch.object(mevzuat, "kaynak_yukle",
                              return_value={"mevzuat": kayitlar})
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(motor, "cek", side_effect=lambda m, eski: cevaplar[m["slug"]])
        p.start()
        self.addCleanup(p.stop)

    def _kos(self, kuru=False):
        with contextlib.redirect_stdout(io.StringIO()):
            return mevzuat._kos([], kuru, "TEST")

    def _diskteki(self):
        with open(motor.DURUM, encoding="utf-8") as f:
            return json.load(f)

    # ────────────────────────────────────────────────────────────────────────
    def test_metin_imzasi_ayni_cikinca_damga_guncellenir(self):
        """Asıl hata: 'ayni' (metin hash'i) sonucunda damga hiç basılmıyordu."""
        self._kur(
            [_kayit("k-304", tur="Kanun"), _kayit("y-ayni"), _kayit("y-hata")],
            {"k-304": {"imza": "bayt", "etag": '"e1"', "son_dogrulama": ESKI},
             "y-ayni": {"imza": c.sha(METIN_AYNI), "son_dogrulama": ESKI},
             "y-hata": {"imza": "x", "son_dogrulama": ESKI}},
            {"k-304": {"sonuc": "degismemis"},
             "y-ayni": _ok(METIN_AYNI),
             "y-hata": {"sonuc": "hata", "not": "HTTP 000"}})

        self.assertEqual(self._kos(), 1)      # 1 = ulaşılamayan var
        d = self._diskteki()
        for slug in ("k-304", "y-ayni"):
            self.assertNotEqual(d[slug]["son_dogrulama"], ESKI, slug)
            self.assertRegex(d[slug]["son_dogrulama"], BICIM, slug)
        self.assertEqual(d["y-hata"]["son_dogrulama"], ESKI,
                         "ulaşılamayan kayıt 'doğrulandı' sayılamaz")
        self.assertEqual(d["y-ayni"]["imza"], c.sha(METIN_AYNI),
                         "yalnız damga değişir, imzaya dokunulmaz")

    def test_devre_kesici_tetiklenince_hicbir_damga_basilmaz(self):
        """Kesici tetiklendiyse koşunun ölçümüne güvenilmez; 304 dahil hiçbir
        kayıt 'doğrulandı' diye damgalanmaz. Eskiden 304 dalı damgayı bellekteki
        `durum`a basıyordu ve aynı koşudaki bir 'ilk' indirme, artımlı kayıtla
        onu kesiciden ÖNCE diske sızdırıyordu."""
        degisen = [f"y-deg{i}" for i in range(3)]
        self._kur(
            [_kayit("k-304", tur="Kanun"), _kayit("y-ayni"), _kayit("y-yeni")]
            + [_kayit(s) for s in degisen],
            {"k-304": {"imza": "bayt", "etag": '"e1"', "son_dogrulama": ESKI},
             "y-ayni": {"imza": c.sha(METIN_AYNI), "son_dogrulama": ESKI},
             **{s: {"imza": c.sha(METIN_AYNI), "son_dogrulama": ESKI} for s in degisen}},
            {"k-304": {"sonuc": "degismemis"},
             "y-ayni": _ok(METIN_AYNI),
             "y-yeni": _ok(METIN_AYNI),         # 'ilk' → döngü içinde diske yazılır
             **{s: _ok(METIN_YENI) for s in degisen}})   # 3/5 = %60 'değişti'

        self.assertEqual(self._kos(), 3)
        d = self._diskteki()
        self.assertIn("y-yeni", d, "ilk indirme kesiciden bağımsız yazılır")
        for slug in ["k-304", "y-ayni"] + degisen:
            self.assertEqual(d[slug]["son_dogrulama"], ESKI, slug)
        for slug in degisen:
            self.assertEqual(d[slug]["imza"], c.sha(METIN_AYNI), slug)

    def test_kuru_kosu_durum_dosyasina_dokunmaz(self):
        self._kur(
            [_kayit("k-304", tur="Kanun"), _kayit("y-ayni")],
            {"k-304": {"imza": "bayt", "etag": '"e1"', "son_dogrulama": ESKI},
             "y-ayni": {"imza": c.sha(METIN_AYNI), "son_dogrulama": ESKI}},
            {"k-304": {"sonuc": "degismemis"}, "y-ayni": _ok(METIN_AYNI)})
        with open(motor.DURUM, "rb") as f:
            once = f.read()

        self.assertEqual(self._kos(kuru=True), 0)
        with open(motor.DURUM, "rb") as f:
            self.assertEqual(f.read(), once)

    def test_kalem_durumu_degistirmez(self):
        """kalem() yalnız sonuç döndürür; `durum`a yazma devre kesiciden sonra
        `_kos`'ta yapılır. Damga, kontrolün yapıldığı anı taşır."""
        durum = {"k-304": {"imza": "bayt", "etag": '"e1"', "son_dogrulama": ESKI},
                 "y-ayni": {"imza": c.sha(METIN_AYNI), "son_dogrulama": ESKI}}
        cevap = {"k-304": {"sonuc": "degismemis"}, "y-ayni": _ok(METIN_AYNI)}
        once = json.dumps(durum, sort_keys=True)
        with mock.patch.object(motor, "cek", side_effect=lambda m, e: cevap[m["slug"]]):
            s304 = motor.kalem(_kayit("k-304", tur="Kanun"), durum)
            smet = motor.kalem(_kayit("y-ayni"), durum)
        self.assertEqual(json.dumps(durum, sort_keys=True), once)
        for s in (s304, smet):
            self.assertEqual(s["sonuc"], "ayni")
            self.assertRegex(s["dogrulama_zamani"], BICIM)


if __name__ == "__main__":
    unittest.main()
