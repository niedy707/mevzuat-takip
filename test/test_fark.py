# -*- coding: utf-8 -*-
"""Kelime düzeyinde fark (Ö-3) ve hibrit tespit kararı (Ö-8) testleri."""
import difflib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cekirdek  # noqa: E402


class KelimeFarki(unittest.TestCase):

    def opcodes(self, a, b, autojunk):
        return difflib.SequenceMatcher(None, a.split(), b.split(),
                                       autojunk=autojunk).get_opcodes()

    def test_autojunk_kapali_olmali(self):
        """difflib'in `autojunk=True` varsayılanı, 200'den uzun dizilerde çok
        tekrar eden öğeleri 'junk' sayar. Mevzuat metninde bu tam olarak
        've', 'madde', 'fıkra' demektir — fark anlamsızlaşır."""
        a = ("ve madde " * 120) + "altı iş günü"
        b = ("ve madde " * 120) + "otuz iş günü"
        kapali = [o for o in self.opcodes(a, b, False) if o[0] != "equal"]
        self.assertEqual(len(kapali), 1,
                         "autojunk=False tek ve net bir değişiklik bulmalı")
        etiket, i1, i2, j1, j2 = kapali[0]
        self.assertEqual(etiket, "replace")
        self.assertEqual(a.split()[i1:i2], ["altı"])
        self.assertEqual(b.split()[j1:j2], ["otuz"])

    def test_gercek_mevzuat_degisikligi(self):
        a = "Fesih bildirimi altı iş günü içinde yapılır."
        b = "Fesih bildirimi otuz iş günü içinde yapılır."
        deg = [o for o in self.opcodes(a, b, False) if o[0] != "equal"]
        self.assertEqual(len(deg), 1)


class HibritTespit(unittest.TestCase):
    """Ö-8: hangi kayıt hangi imzayla izlenir.
    ÖLÇÜM (19.09.2026): statik kanun PDF'i iki indirmede bayt-aynı ve ETag
    veriyor; GeneratePdf yönetmeliği aynı boyutta farklı sha üretiyor, ETag yok."""

    def test_kanun_ve_khk_statiktir(self):
        for tur in ("Kanun", "KHK"):
            self.assertTrue(cekirdek.statik_mi({"tur": tur}))

    def test_yonetmelik_ve_teblig_uretilir(self):
        for tur in ("KurumVeKurulusYonetmeligi", "BakanlarKuruluYonetmeligi", "Teblig"):
            self.assertFalse(cekirdek.statik_mi({"tur": tur}))

    def test_statik_adres_kalibi(self):
        m = {"tur": "Kanun", "tur_no": 1, "tertip": "5", "no": "4857"}
        self.assertEqual(cekirdek.adresler(m)[0],
                         "https://www.mevzuat.gov.tr/MevzuatMetin/1.5.4857.pdf")

    def test_yonetmelik_once_generatepdf_dener(self):
        m = {"tur": "KurumVeKurulusYonetmeligi", "tur_no": 7,
             "tertip": "5", "no": "5451"}
        a = cekirdek.adresler(m)
        self.assertIn("GeneratePdf", a[0])
        self.assertTrue(any("yonetmelik/7.5.5451.pdf" in x for x in a),
                        "statik yol yedek olarak denenmeli")

    def test_elle_verilen_adres_once_denenir(self):
        m = {"tur": "KurumVeKurulusYonetmeligi", "tur_no": 7, "tertip": "5",
             "no": "4883", "url_adaylari": ["https://ornek/oncelikli.pdf"]}
        self.assertEqual(cekirdek.adresler(m)[0], "https://ornek/oncelikli.pdf")


class Normalizasyon(unittest.TestCase):

    def test_nfkc_ligatur_cozer_turkceyi_bozmaz(self):
        s = cekirdek.normalize("ﬁnansal ² İstanbul ılık\n")
        self.assertIn("finansal", s)
        self.assertIn("2", s)
        self.assertIn("İstanbul", s)
        self.assertIn("ılık", s)

    def test_sayfa_sonu_ve_bos_satir_yiginlari(self):
        a = cekirdek.normalize("Bir\n\n\n\nİki\n")
        b = cekirdek.normalize("Bir\n\nİki\n")
        self.assertEqual(a, b)
        self.assertNotIn("\f", cekirdek.normalize("Bir\fİki"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
