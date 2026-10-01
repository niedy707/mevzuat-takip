# -*- coding: utf-8 -*-
"""Yayın (public sayfa) ve acil süzgeci testleri — yayin.py, acil_is.py.

Ağa ÇIKMAZ, Vercel'e yüklemez, bildirim göndermez.
En önemli sınama GİZLİLİK: sayfa public'tir; kaynak.json `neden` alanları
(dava gerekçesi) ve olay kaydının iç notları sayfaya GİREMEZ.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import acil_is  # noqa: E402
import yayin  # noqa: E402


def kalem(**k):
    temel = {"kimlik": "O-1", "anahtarlar": ["O-1"], "kaynak": "mevzuat", "siddet": "kritik",
             "slug": "y-ozel-hastaneler", "baslik": "Özel Hastaneler Yönetmeliği",
             "ozet": "m.24 değişti", "madde": "24", "kritik_madde": True,
             "zaman": datetime.now().isoformat(timespec="seconds"), "tarih": "26.09.2026"}
    temel.update(k)
    return temel


class Gizlilik(unittest.TestCase):

    def test_olay_karti_ic_notlari_tasimaz(self):
        olay = {"id": "O-1", "slug": "yok-boyle-belge", "ad": "Deneme Yönetmeliği",
                "madde": "", "tur_adi": "madde metni değişti", "tarih": "26.09.2026 09:00",
                "ozet": "m.3 değişti", "kunye": "",
                "not": "GİZLİ-NOT is-hukuku dava dosyası",
                "kaynak": "GİZLİ-KAYNAK geçiş karşılaştırması",
                "neden": "GİZLİ-NEDEN işverenin statüsü"}
        h = yayin._olay_karti(kalem(slug="yok-boyle-belge"), olay,
                              {"sayfa_url": "https://www.mevzuat.gov.tr/mevzuat?x=1"})
        for gizli in ("GİZLİ-NOT", "GİZLİ-KAYNAK", "GİZLİ-NEDEN", "is-hukuku"):
            self.assertNotIn(gizli, h)
        self.assertIn("https://www.mevzuat.gov.tr/mevzuat?x=1", h)   # link ZORUNLU

    def test_html_kacislanir(self):
        olay = {"id": "O-1", "slug": "x", "ad": "<b>Ad</b>", "madde": "",
                "tur_adi": "t", "tarih": "", "ozet": "<script>alert(1)</script>", "kunye": ""}
        h = yayin._olay_karti(kalem(slug="x"), olay, {})
        self.assertNotIn("<script>", h)
        self.assertIn("&lt;script&gt;", h)

    def test_izlenen_slug_yerine_ad(self):
        k = {"mevzuat": [{"slug": "y-uzaktan-calisma", "ad": "Uzaktan Çalışma Yönetmeliği"}]}
        self.assertEqual(yayin._izlenen_ad("izlenen: y-uzaktan-calisma", k),
                         "izlenen belge: Uzaktan Çalışma Yönetmeliği")


class KelimeFarki(unittest.TestCase):

    def test_silinen_eklenen_ve_kacis(self):
        h = yayin.kelime_farki_html("madde (şerh: <eski>) yürürlükte",
                                    "madde yürürlükte <yeni>")
        self.assertIn("<del>", h)
        self.assertIn("<ins>&lt;yeni&gt;</ins>", h)
        self.assertNotIn("<eski>", h)

    def test_uzun_esit_blok_kisaltilir(self):
        ortak = " ".join(f"k{i}" for i in range(50))
        h = yayin.kelime_farki_html(ortak + " eski", ortak + " yeni")
        self.assertIn("…", h)
        self.assertNotIn("k20 ", h)


class BildirimMetni(unittest.TestCase):

    def test_degisiklik_yoksa_da_bildirim_var(self):
        b, g = yayin.bildirim_metni("gunluk", [], [], [])
        self.assertEqual(b, "✅ Mevzuat günlük: değişiklik yok")
        self.assertIn("Dokun", g)

    def test_kritik_baslik(self):
        b, _ = yayin.bildirim_metni("gunluk", [kalem()], [], [])
        self.assertTrue(b.startswith("🚨 Mevzuat günlük: 1 kayıt (1 kritik)"))

    def test_yalniz_uyari(self):
        b, g = yayin.bildirim_metni("gunluk", [], [], [], ["DEVRE KESİCİ"])
        self.assertTrue(b.startswith("⚠️"))
        self.assertIn("DEVRE KESİCİ", g)

    def test_acil_baslik_ve_aym_satiri(self):
        aym = [kalem(aym="bireysel", saglik=True, aym_isaret="❗", kaynak="rg")]
        b, g = yayin.bildirim_metni("acil", [kalem()], [], aym)
        self.assertTrue(b.startswith("🚨 Mevzuat ACİL"))
        self.assertIn("AYM: 1 karar · 1 🩺 · 1 ❗", g)


class AcilSuzgeci(unittest.TestCase):
    """Kullanıcı kararı 26.09.2026: çekirdek belgelerde kritik/önemli olay,
    çekirdek belgeyi anan RG kaydı ve her YD kaydı ACİL'dir."""
    CEKIRDEK = {"y-ozel-hastaneler", "4857-is-kanunu"}

    def test_madde_olayi(self):
        self.assertTrue(acil_is.acil_mi(kalem(), self.CEKIRDEK))
        self.assertTrue(acil_is.acil_mi(kalem(siddet="onemli"), self.CEKIRDEK))
        self.assertFalse(acil_is.acil_mi(kalem(siddet="bilgi"), self.CEKIRDEK))
        self.assertFalse(acil_is.acil_mi(kalem(slug="6100-hmk"), self.CEKIRDEK))   # destek/yan

    def test_rg_kaydi(self):
        rg = dict(kaynak="rg", aym="", siddet="kritik")
        self.assertTrue(acil_is.acil_mi(kalem(slug="4857-is-kanunu", **rg), self.CEKIRDEK))
        self.assertTrue(acil_is.acil_mi(
            kalem(slug="", ozet="YÜRÜTMENİN DURDURULMASI", **rg), self.CEKIRDEK))
        self.assertFalse(acil_is.acil_mi(kalem(slug="", ozet="sağlık mevzuatı", **rg),
                                         self.CEKIRDEK))

    def test_aym_acil_degil(self):
        self.assertFalse(acil_is.acil_mi(kalem(kaynak="rg", aym="norm"), self.CEKIRDEK))

    def test_islenmis_ve_taze(self):
        k = kalem(kimlik="RG-x", anahtarlar=["2026-09-26|başlık"])
        self.assertTrue(acil_is.islenmis_mi(k, {"acil_bildirilen": {"RG-x": "…"}}))
        self.assertTrue(acil_is.islenmis_mi(k, {"gunluk_yayinlanan": ["2026-09-26|başlık"]}))
        self.assertFalse(acil_is.islenmis_mi(k, {}))
        eski = (datetime.now() - timedelta(days=10)).isoformat(timespec="seconds")
        self.assertFalse(acil_is.taze_mi(kalem(zaman=eski)))
        self.assertTrue(acil_is.taze_mi(kalem()))


class AcilSecimi(unittest.TestCase):
    """Arayüzden seçilen acil listesi (26.09.2026)."""
    KAYNAK = {"mevzuat": [{"slug": "a", "sinif": "cekirdek"}, {"slug": "b", "sinif": "destek"},
                          {"slug": "c", "sinif": "yan"}]}

    def setUp(self):
        import tempfile
        from unittest import mock
        self.td = tempfile.TemporaryDirectory()
        self.yama = mock.patch.object(acil_is, "ACIL_SECIM",
                                      os.path.join(self.td.name, "acil-secim.json"))
        self.yama.start()

    def tearDown(self):
        self.yama.stop()
        self.td.cleanup()

    def test_dosya_yoksa_cekirdek(self):
        self.assertEqual(acil_is.acil_sluglar(self.KAYNAK), {"a"})

    def test_ekle_cikar_kalici(self):
        self.assertEqual(acil_is.acil_secim_degistir("b", True, self.KAYNAK), {"a", "b"})
        self.assertEqual(acil_is.acil_sluglar(self.KAYNAK), {"a", "b"})
        self.assertEqual(acil_is.acil_secim_degistir("a", False, self.KAYNAK), {"b"})
        self.assertEqual(acil_is.acil_secim_degistir("b", False, self.KAYNAK), set())
        self.assertEqual(acil_is.acil_sluglar(self.KAYNAK), set())   # boş ≠ varsayılan

    def test_bilinmeyen_belge_reddedilir(self):
        with self.assertRaises(ValueError):
            acil_is.acil_secim_degistir("../../etc", True, self.KAYNAK)

    def test_izlemeden_cikan_belge_duser(self):
        acil_is.acil_secim_degistir("c", True, self.KAYNAK)
        daralan = {"mevzuat": [m for m in self.KAYNAK["mevzuat"] if m["slug"] != "c"]}
        self.assertEqual(acil_is.acil_sluglar(daralan), {"a"})


class Ayarlar(unittest.TestCase):

    def test_acil_saatleri_plist_ile_ayni(self):
        yol = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "com.mevzuat.acil.plist")
        with open(yol, encoding="utf-8") as f:
            icerik = f.read()
        import re
        saatler = tuple(int(x) for x in re.findall(r"<key>Hour</key><integer>(\d+)</integer>", icerik))
        self.assertEqual(saatler, yayin.ACIL_SAATLER)


if __name__ == "__main__":
    unittest.main()
