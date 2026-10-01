# -*- coding: utf-8 -*-
"""Resmî Gazete süzgeci testleri (Ö-1).

Süzgeç 20.08–19.09.2026 arası 31 günlük GERÇEK fihrist üzerinde kalibre edildi.
Aşağıdaki başlıkların hepsi o taramadan alınmıştır.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rg  # noqa: E402


def saglik_mi(baslik):
    k = rg.tr_kucult(baslik)
    return bool(rg.SAGLIK.search(k)) and not bool(rg.GURULTU.search(k))


class TurkceKucultme(unittest.TestCase):
    """Python'un re.IGNORECASE'i Unicode katlaması yaptığı için `ı` ve `i`
    ikisi de `I`'ya katlanır ve BİRBİRİYLE EŞLEŞİR. Bu yüzden 'tıp ' deseni
    'Tip Onayı' ifadesini yakalıyordu ve motorlu araç tip onayı yönetmeliği
    'sağlık mevzuatı' sayılıyordu (19.09.2026'da ölçüldü)."""

    def test_noktali_noktasiz_i_ayrimi(self):
        self.assertEqual(rg.tr_kucult("TIBBİ"), "tıbbi")
        self.assertEqual(rg.tr_kucult("Tip"), "tip")
        self.assertEqual(rg.tr_kucult("İLAÇ"), "ilaç")
        self.assertNotEqual(rg.tr_kucult("Tip"), rg.tr_kucult("Tıp"))

    def test_tip_onayi_saglik_sayilmaz(self):
        self.assertFalse(saglik_mi(
            "Motorlu Araçlar ve Römorkları ile Bunların Aksam, Sistem ve Ayrı "
            "Teknik Ünitelerinin Tip Onayı ve Piyasa Gözetimi Hakkında Yönetmelik"))


class SaglikSuzgeci(unittest.TestCase):

    def test_gercek_saglik_kayitlari(self):
        for b in [
            "Özel Hastaneler Yönetmeliğinde Değişiklik Yapılmasına Dair Yönetmelik",
            "Sosyal Güvenlik Kurumu Sağlık Uygulama Tebliğinde Değişiklik Yapılmasına Dair Tebliğ",
            "Beşeri Tıbbi Ürünlerin Fiyatlandırılması Hakkında Tebliğ",
            "Sağlık Hizmetleri Fiyatlandırma Komisyonu Kararı",
            "Ambulans ve Acil Bakım Teknikerleri ile Acil Tıp Teknisyenlerinin Çalışma Usul ve Esasları",
            "Tıbbi Cihaz Yönetmeliği Kapsamında Yapılacak Denetimler",
            "Türk Optisyen-Gözlükçüler Birliği Yönetmeliği",
            "Çocukluk Çağı Aşı Takvimi Hakkında Tebliğ",
        ]:
            self.assertTrue(saglik_mi(b), f"sağlık sayılmalıydı: {b}")

    def test_universite_ic_mevzuati_elenir(self):
        """31 günde 18 sağlık eşleşmesinin 8'i üniversite iç mevzuatıydı;
        klinik uygulamayı ilgilendirmez."""
        for b in [
            "Mersin Üniversitesi Diş Hekimliği Fakültesi Eğitim-Öğretim ve Sınav Yönetmeliği",
            "Burdur Mehmet Akif Ersoy Üniversitesi Tıp Fakültesi Eğitim-Öğretim ve Sınav Yönetmeliği",
            "Kafkas Üniversitesi Ağız ve Diş Sağlığı Uygulama ve Araştırma Merkezi Yönetmeliği",
            "Bingöl Üniversitesi Veteriner Sağlık Uygulama ve Araştırma Merkezi Yönetmeliği",
        ]:
            self.assertFalse(saglik_mi(b), f"elenmeliydi: {b}")

    def test_kamulastirma_elenir(self):
        """'gölbaşı' kelimesi sınırsız `aşı` desenine takılıyordu."""
        self.assertFalse(saglik_mi(
            "Ankara İli, Gölbaşı İlçesinde Kurulacak Doğal Gaz Dağıtım Tesisinin "
            "Yapımı Amacıyla Bazı Taşınmazların Kamulaştırılması Hakkında Karar"))

    def test_fakulte_ad_degisikligi_elenir(self):
        self.assertFalse(saglik_mi(
            "Amasya Üniversitesi Rektörlüğü Bünyesinde Bilgisayar ve Bilişim "
            "Bilimleri Fakültesi Kurulması, Diş Hekimliği Fakültesinin Adının "
            "Değiştirilmesi Hakkında Karar"))


class KayitSuzme(unittest.TestCase):

    def kayit(self, bolum, kategori, baslik):
        return [{"bolum": bolum, "kategori": kategori, "baslik": baslik,
                 "url": "", "ilan": "İLÂN" in bolum}]

    def test_ilan_bolumu_tamamen_elenir(self):
        """Kullanıcı kararı (19.09.2026): ilan ve duyurulara gerek yok.
        DİKKAT: İLÂN bölümünde alt kategori bir öncekinden DEVRALINIYOR,
        bu yüzden eleme ÜST BÖLÜME göre yapılmalı."""
        k = self.kayit("İLÂN BÖLÜMÜ", "ANAYASA MAHKEMESİ KARARLARI",
                       "a - Artırma, Eksiltme ve İhale İlânları")
        self.assertEqual(rg.suz(k), [])

    def test_aym_karari_kritik(self):
        k = self.kayit("YARGI BÖLÜMÜ", "ANAYASA MAHKEMESİ KARARLARI",
                       "Anayasa Mahkemesinin 13/5/2026 Tarihli ve E: 2026/41 Sayılı Kararı")
        s = rg.suz(k)
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["siddet"], "kritik")
        self.assertIn("Anayasa Mahkemesi kararı", s[0]["sebep"])

    def test_danistay_karari_kritik(self):
        k = self.kayit("YÜRÜTME VE İDARE BÖLÜMÜ", "DANIŞTAY KARARI",
                       "Danıştay Altıncı Dairesine Ait Karar")
        s = rg.suz(k)
        self.assertEqual(s[0]["siddet"], "kritik")

    def test_izlenen_belge_kanun_numarasiyla_yakalanir(self):
        izlenen = [{"slug": "193-gelir-vergisi", "ad": "Gelir Vergisi Kanunu",
                    "no": "193", "tur": "Kanun"}]
        k = self.kayit("YÜRÜTME VE İDARE BÖLÜMÜ", "CUMHURBAŞKANI KARARLARI",
                       "193 Sayılı Gelir Vergisi Kanununun Geçici 67 nci Maddesinde "
                       "Yer Alan Tevkifat Oranları Hakkında Karar")
        s = rg.suz(k, izlenen)
        self.assertEqual(s[0]["siddet"], "kritik")
        self.assertTrue(any("193-gelir-vergisi" in x for x in s[0]["sebep"]))

    def test_izlenen_belge_adiyla_yakalanir(self):
        izlenen = [{"slug": "y-ozel-hastaneler", "ad": "Özel Hastaneler Yönetmeliği",
                    "no": "41265", "tur": "KurumVeKurulusYonetmeligi"}]
        k = self.kayit("YÜRÜTME VE İDARE BÖLÜMÜ", "YÖNETMELİKLER",
                       "Özel Hastaneler Yönetmeliğinde Değişiklik Yapılmasına Dair Yönetmelik")
        s = rg.suz(k, izlenen)
        self.assertEqual(s[0]["siddet"], "kritik")

    def test_alakasiz_kayit_elenir(self):
        k = self.kayit("YÜRÜTME VE İDARE BÖLÜMÜ", "ATAMA KARARLARI",
                       "Cumhurbaşkanlığı Tarafından Yapılan Atamalar Hakkında Kararlar")
        self.assertEqual(rg.suz(k), [])

    def test_epdk_kurul_karari_yakalanir(self):
        """EPDK Kurul Kararı fihristte KONUSUNU YAZMAZ — 20.09.2026'da 180 günlük
        gerçek fihrist tarandı, 24 kaydın hiçbirinde 'son kaynak'/'serbest tüketici'
        ibaresi geçmiyordu. Bu yüzden süzgeç kuruma bakar, konuya değil.
        Bu başlık RG 31.10.2025-33063'ten birebir alınmıştır: o karar mesken
        son kaynak eşiğini 2026 için 4.000 kWh/yıl'a indiren karardır."""
        k = self.kayit("YÜRÜTME VE İDARE BÖLÜMÜ", "KURUL KARARLARI",
                       "Enerji Piyasası Düzenleme Kurulunun 30/10/2025 Tarihli ve "
                       "13912 Sayılı Kararı")
        s = rg.suz(k)
        self.assertEqual(len(s), 1)
        self.assertTrue(any("EPDK Kurul Kararı" in x for x in s[0]["sebep"]))

    def test_epdk_karari_kritige_yukseltilmez(self):
        """Ayda ortalama 4 kayıt (ölçüldü) — 'kritik' demek kurt masalı olurdu."""
        k = self.kayit("YÜRÜTME VE İDARE BÖLÜMÜ", "KURUL KARARI",
                       "Enerji Piyasası Düzenleme Kurulunun 18/12/2025 Tarihli ve "
                       "14039 Sayılı Kararı")
        self.assertEqual(rg.suz(k)[0]["siddet"], "onemli")

    def test_diger_kurul_kararlari_elenir(self):
        """Süzgeç 'kurul kararı' ibaresine değil, EPDK'ye bakar."""
        k = self.kayit("YÜRÜTME VE İDARE BÖLÜMÜ", "KURUL KARARLARI",
                       "Bankacılık Düzenleme ve Denetleme Kurulunun 11/09/2026 "
                       "Tarihli ve 12034 Sayılı Kararı")
        self.assertEqual(rg.suz(k), [])

    def test_yurutme_durdurma_ibaresi_kritik(self):
        k = self.kayit("YARGI BÖLÜMÜ", "DANIŞTAY KARARI",
                       "Bazı Maddelerin Yürütmesinin Durdurulmasına İlişkin Karar")
        s = rg.suz(k)
        self.assertEqual(s[0]["siddet"], "kritik")


if __name__ == "__main__":
    unittest.main(verbosity=2)
