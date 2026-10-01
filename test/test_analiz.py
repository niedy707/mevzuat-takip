# -*- coding: utf-8 -*-
"""Madde ayrıştırıcısı ve olay üretimi testleri.

Her test, 19.09.2026'da GERÇEK külliyatta ölçülmüş bir tuzağa karşılık gelir.
Tuzaklar bulunmadan önce ayrıştırıcı sessizce yanlış envanter üretiyordu —
bir mevzuat izleyicisinde bu, olmayan değişikliği bildirmek ya da olanı
kaçırmak demektir.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import analiz  # noqa: E402


class MaddeAyristirma(unittest.TestCase):

    def test_temel_bicimler(self):
        m = ("Madde 1 – Birinci madde metni.\n"
             "MADDE 2- (1) İkinci madde.\n"
             "Ek Madde 3 – Ek madde metni.\n"
             "GEÇİCİ MADDE 4- Geçici madde.\n")
        env, muk = analiz.envanter(m)
        self.assertEqual(set(env), {"1", "2", "Ek 3", "Geçici 4"})
        self.assertEqual(muk, [])

    def test_mukerrer_madde_ayri_maddedir(self):
        """Gelir Vergisi'nde 'Mükerrer Madde 121' m.121'den AYRIDIR (193'te 48 kez).
        Ön ek yakalanmazsa ikisi aynı anahtara düşer ve biri sessizce kaybolur."""
        m = ("Madde 121 – Normal madde.\n"
             "Mükerrer Madde 121 – Mükerrer madde, bambaşka bir hüküm.\n")
        env, muk = analiz.envanter(m)
        self.assertIn("121", env)
        self.assertIn("Mükerrer 121", env)
        self.assertEqual(muk, [], "mükerrer ön eki çakışma üretmemeli")
        self.assertNotEqual(env["121"]["sha"], env["Mükerrer 121"]["sha"])

    def test_harf_ekli_madde_ayri_maddedir(self):
        """'Madde 98/A' m.98'den ayrıdır. Külliyatta 13/A, 17/A-B, 183/A yaygın."""
        m = ("Madde 98 – Doksan sekizinci madde.\n"
             "Madde 98/A- (Ek: 15/7/2016-6728/16 md.) Muhtasar beyanname.\n")
        env, _ = analiz.envanter(m)
        self.assertEqual(set(env), {"98", "98/A"})

    def test_kuyruk_dizini_govdeye_karismaz(self):
        """Kanun sonundaki 'İŞLENEMEYEN GEÇİCİ MADDELER' bölümünde değiştiren
        kanunların KENDİ geçici maddeleri tekrar basılır. Gövdeye katılırsa
        'Geçici Madde 1' birden çok kez görünür (193'te tam olarak bu oldu).
        İşaret 'İŞLENEMEYEN HÜKÜM' DEĞİL, 'İŞLENEMEYEN GEÇİCİ MADDELER'dir."""
        m = ("Madde 1 – Gerçek madde.\n"
             "Geçici Madde 1 – Gerçek geçici madde.\n"
             "31/12/1960 TARİH VE 193 SAYILI KANUNA\n"
             "İŞLENEMEYEN GEÇİCİ MADDELER:\n"
             "Geçici Madde 1 – Başka kanunun geçici maddesi.\n"
             "Geçici Madde 2 – Bir diğeri.\n")
        env, muk = analiz.envanter(m)
        self.assertEqual(set(env), {"1", "Geçici 1"})
        self.assertEqual(muk, [], "kuyruk kesildiği için mükerrer oluşmamalı")

    def test_ek_ve_degisiklik_tablosu_kesilir(self):
        m = ("Madde 5 – Metin.\n"
             "4857 SAYILI KANUNA EK VE DEĞİŞİKLİK GETİREN MEVZUATIN\n"
             "Madde 99 – tablodaki sahte madde\n")
        env, _ = analiz.envanter(m)
        self.assertEqual(set(env), {"5"})

    def test_cumle_icindeki_madde_atfi_eslesmez(self):
        """'... 98 inci madde gereğince ...' bir madde BAŞLIĞI değildir.
        Ayraç zorunlu olmasaydı yanlış eşleşirdi."""
        m = ("Madde 3 – Bu hükümde 98 inci madde gereğince işlem yapılır.\n"
             "94 üncü madde gereğince tevkifat yapılır.\n")
        env, _ = analiz.envanter(m)
        self.assertEqual(set(env), {"3"})


class DurumTespiti(unittest.TestCase):

    def test_yurutme_durdurma(self):
        m = ("MADDE 24- (1) (Danıştay Onuncu Dairesinin 31/12/2025 tarihli ve "
             "E.:2025/1600 sayılı kararı ile yürütmesi durdurulan fıkra: Özel "
             "hastaneler kadro sınırlaması.)\n")
        env, _ = analiz.envanter(m)
        self.assertEqual(env["24"]["durum"], "yurutme_durduruldu")
        self.assertIn("2025/1600", env["24"]["kunye"])

    def test_aym_iptali(self):
        m = ("Madde 78 – (İptal ikinci cümle: Anayasa Mahkemesi’nin 25/12/2014 "
             "tarihli ve E.: 2014/74, K.: 2014/201 sayılı Kararı ile.)\n")
        env, _ = analiz.envanter(m)
        self.assertEqual(env["78"]["durum"], "iptal")
        self.assertIn("2014/74", env["78"]["kunye"])

    def test_mulga(self):
        m = "Madde 33 - (Mülga: 4/12/1985-3239/138 md.)\n"
        env, _ = analiz.envanter(m)
        self.assertEqual(env["33"]["durum"], "mulga")


class DipnotAyirma(unittest.TestCase):
    """Ö-10: pdftotext -layout sayfa altı dipnotlarını metin akışına serpiştirir.
    ÖLÇÜM: 4857'de 132 maddenin 22'sinin gövdesine dipnot bloğu düşüyor.
    Ayrılmazsa m.5'e dipnot eklenmesi m.80'in hash'ini değiştirir."""

    def test_dipnot_govde_hashini_etkilemez(self):
        temiz = "Madde 80 – Seksen maddesinin metni buradadır.\n"
        dipnotlu = ("Madde 80 – Seksen maddesinin metni buradadır.\n"
                    "1\n"
                    "2/7/2018 tarihli ve 700 sayılı KHK'nin 145 inci maddesiyle "
                    "bu fıkrada değişiklik yapılmıştır.\n")
        a, _ = analiz.envanter(temiz)
        b, _ = analiz.envanter(dipnotlu)
        self.assertEqual(a["80"]["sha"], b["80"]["sha"],
                         "dipnot bloğu gövde hash'ini değiştirmemeli")
        self.assertTrue(b["80"]["dipnot_blok"], "dipnot ayrı alanda saklanmalı")


class OlayUretimi(unittest.TestCase):

    def kur(self, metin):
        return analiz.envanter(metin)[0]

    def test_madde_eklendi_ve_kaldirildi(self):
        eski = self.kur("Madde 1 – Bir.\nMadde 2 – İki.\n")
        yeni = self.kur("Madde 1 – Bir.\nMadde 3 – Üç.\n")
        tur = {o["tur"] for o in analiz.karsilastir(eski, yeni)}
        self.assertEqual(tur, {"madde_eklendi", "madde_kaldirildi"})

    def test_kaldirma_kritiktir(self):
        eski = self.kur("Madde 1 – Bir.\nMadde 2 – İki.\n")
        yeni = self.kur("Madde 1 – Bir.\n")
        o = analiz.karsilastir(eski, yeni)[0]
        self.assertEqual(o["siddet"], "kritik")

    def test_yurutme_durdurma_olayi(self):
        eski = self.kur("MADDE 5- (1) Sağlık kuruluşu şu şartları taşır.\n")
        yeni = self.kur("MADDE 5- (1) (Danıştay Onuncu Dairesinin 17/12/2025 "
                        "tarihli ve E.:2025/4140 sayılı kararı ile yürütmesi "
                        "durdurulan ibare) Sağlık kuruluşu şu şartları taşır.\n")
        o = analiz.karsilastir(eski, yeni)
        self.assertEqual(o[0]["tur"], "yurutme_durduruldu")
        self.assertEqual(o[0]["siddet"], "kritik")

    def test_yurutme_durdurma_kalkmasi(self):
        """Kullanıcının açıkça istediği ikinci yön: durdurmanın İPTALİ."""
        eski = self.kur("MADDE 5- (1) (Danıştay kararı ile yürütmesi durdurulan "
                        "ibare) Metin.\n")
        yeni = self.kur("MADDE 5- (1) Metin.\n")
        o = analiz.karsilastir(eski, yeni)
        self.assertEqual(o[0]["tur"], "yurutme_durdurma_kalkti")
        self.assertEqual(o[0]["siddet"], "kritik")

    def test_kritik_madde_degisimi_yukseltilir(self):
        eski = self.kur("Madde 17 – Altı iş günü içinde.\n")
        yeni = self.kur("Madde 17 – Otuz iş günü içinde.\n")
        normal = analiz.karsilastir(eski, yeni)
        self.assertEqual(normal[0]["siddet"], "onemli")
        yukseltilmis = analiz.karsilastir(eski, yeni, kritik_madde=["17"])
        self.assertEqual(yukseltilmis[0]["siddet"], "kritik")

    def test_ayni_metin_olay_uretmez(self):
        e = self.kur("Madde 1 – Bir.\n")
        self.assertEqual(analiz.karsilastir(e, e), [])

    def test_siralama(self):
        self.assertEqual(
            sorted(["Geçici 2", "17", "Ek 1", "98/A", "2"], key=analiz._sirala),
            ["2", "17", "98/A", "Ek 1", "Geçici 2"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
