# -*- coding: utf-8 -*-
"""Değişiklik raporu testleri (degisiklik.py).

Ağa ÇIKMAZ: RG belgesi indirme ve OCR yolu burada sınanmaz; liste/gruplama,
numara kalıcılığı, eski nüshayı farktan geri kurma ve etki süzgeci sınanır.
"""
import difflib
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import degisiklik as dg  # noqa: E402


def kalem(kimlik, zaman, anahtarlar=None, kaynak="mevzuat"):
    return {"kimlik": kimlik, "anahtarlar": anahtarlar or [kimlik], "kaynak": kaynak,
            "zaman": zaman, "tarih": zaman, "siddet": "onemli", "slug": "",
            "baslik": kimlik, "ozet": "", "madde": "", "kritik_madde": False}


class Gruplama(unittest.TestCase):

    def test_yeni_kimlige_gore_zamana_gore_degil(self):
        """RG 3 günlük pencereyle koşar: son rapordan ÖNCE tarihli ama SONRA
        görülen kayıt A grubuna düşmeli, kaybolmamalı."""
        k = [kalem("O-3", "2026-09-25T09:00"), kalem("RG-eski", "2026-09-20T00:00"),
             kalem("O-1", "2026-09-19T09:00")]
        yeni, onceki = dg.grupla(k, raporlanan={"O-3", "O-1"})
        self.assertEqual([x["kimlik"] for x in yeni], ["RG-eski"])
        self.assertEqual([x["kimlik"] for x in onceki], ["O-3", "O-1"])

    def test_onceki_grup_on_ile_sinirli(self):
        k = [kalem(f"O-{i:02d}", f"2026-09-{i:02d}T09:00") for i in range(30, 0, -1)]
        yeni, onceki = dg.grupla(k, raporlanan={x["kimlik"] for x in k})
        self.assertEqual(yeni, [])
        self.assertEqual(len(onceki), 10)
        self.assertEqual(onceki[0]["kimlik"], "O-30")      # en yeni önce

    def test_buyuyen_grup_yeni_sayilir(self):
        """Aynı günün AYM grubuna sonradan bir karar eklenirse grup yeniden A'ya düşer."""
        k = [kalem("RG-G", "2026-09-21T00:00", anahtarlar=["a", "b", "c"], kaynak="rg")]
        yeni, _ = dg.grupla(k, raporlanan={"a", "b"})
        self.assertEqual(len(yeni), 1)
        yeni, onceki = dg.grupla(k, raporlanan={"a", "b", "c"})
        self.assertEqual((len(yeni), len(onceki)), (0, 1))


class RgKalemleri(unittest.TestCase):
    IZLENEN = [{"slug": "y-uzaktan-calisma", "ad": "Uzaktan Çalışma Yönetmeliği",
                "tur": "KurumVeKurulusYonetmeligi", "no": "37329"}]

    def test_aym_kararlari_tek_tek_ve_turuyle(self):
        """AYM kararları ayrı grupta TEK TEK listelenir (kullanıcı kararı 25.09.2026);
        bireysel başvuru 'bilgi', norm denetimi rg.py şiddetiyle (kritik)."""
        a = ["2026-09-21|Anayasa Mahkemesinin 12/3/2026 Tarihli ve 2021/10952 Başvuru Numaralı Kararı",
             "2026-09-21|Anayasa Mahkemesinin 3/3/2026 Tarihli ve 2022/82055 Başvuru Numaralı Kararı",
             "2026-09-18|Anayasa Mahkemesinin 25/6/2026 Tarihli ve E: 2026/71, K: 2026/148 Sayılı Kararı",
             "2026-09-19|Türk Optisyen-Gözlükçüler Birliği Yönetmeliği"]
        k = {x["baslik"][-40:]: x for x in dg.rg_kalemleri(a, self.IZLENEN)}
        self.assertEqual(len(k), 4)
        tur = sorted(x["aym"] for x in k.values())
        self.assertEqual(tur, ["", "bireysel", "bireysel", "norm"])
        for x in k.values():
            if x["aym"] == "bireysel":
                self.assertEqual(x["siddet"], "bilgi")
            if x["aym"] == "norm":
                self.assertEqual(x["siddet"], "kritik")

    def test_kisa_aym_basligi(self):
        self.assertEqual(dg._kisa_aym(
            "Anayasa Mahkemesinin 25/6/2026 Tarihli ve E: 2026/71, K: 2026/148 Sayılı Kararı"),
            "25/6/2026 · E: 2026/71, K: 2026/148")

    def test_izlenen_belge_slug_tasir(self):
        k = dg.rg_kalemleri(
            ["2026-09-25|Uzaktan Çalışma Yönetmeliğinde Değişiklik Yapılması Hakkında Yönetmelik"],
            self.IZLENEN)
        self.assertEqual(k[0]["slug"], "y-uzaktan-calisma")
        self.assertEqual(k[0]["tarih"], "25.09.2026")

    def test_bozuk_anahtar_atlanir(self):
        self.assertEqual(dg.rg_kalemleri(["tarihsiz başlık"], self.IZLENEN), [])


class Numaralar(unittest.TestCase):
    """Numara kalıcı olmalı: "5'i detaylandır" başka oturumda da aynı kalemi bulur."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.yol = os.path.join(self.td.name, "rapor-durum.json")
        self.kalemler = [kalem("O-2", "2026-09-25T09:00"), kalem("O-1", "2026-09-19T09:00")]
        self.yamalar = [mock.patch.object(dg, "RAPOR_DURUM", self.yol),
                        mock.patch.object(dg, "tum_kalemler", lambda: list(self.kalemler)),
                        mock.patch.object(dg, "_tazelik", lambda: (None, None, []))]
        for y in self.yamalar:
            y.start()

    def tearDown(self):
        for y in self.yamalar:
            y.stop()
        self.td.cleanup()

    def kos(self, kuru=False):
        with redirect_stdout(io.StringIO()) as f:
            dg.komut_liste(kuru)
        with open(self.yol, encoding="utf-8") as j:
            return f.getvalue(), json.load(j)

    def test_ilk_rapor_hepsi_yeni_ikinci_rapor_bos(self):
        cikti, d = self.kos()
        self.assertIn("ilk rapor", cikti)
        self.assertEqual([x["grup"] for x in d["liste"]], ["yeni", "yeni"])
        self.kalemler.insert(0, kalem("O-3", "2026-09-26T09:00"))
        _, d = self.kos()
        self.assertEqual([(x["no"], x["kimlik"], x["grup"]) for x in d["liste"]],
                         [(1, "O-3", "yeni"), (2, "O-2", "onceki"), (3, "O-1", "onceki")])

    def test_kuru_isareti_ilerletmez_ama_numarayi_yazar(self):
        _, d = self.kos(kuru=True)
        self.assertNotIn("son_rapor", d)
        self.assertEqual(len(d["liste"]), 2)          # ekrandaki numara detayda bulunur
        _, d = self.kos()
        self.assertEqual({x["grup"] for x in d["liste"]}, {"yeni"})


class GeriKurma(unittest.TestCase):
    ESKI = "BAŞLIK\n\fMADDE 1- (1) Birinci.\nMADDE 2- (1) (Danıştay ... yürütmesi durdurulan fıkra: İkinci.)\nMADDE 3- Son.\n"
    YENI = "BAŞLIK\n\fMADDE 1- (1) Birinci.\nMADDE 2- (1) İkinci.\nMADDE 3- Son.\nMADDE 4- Ek.\n"

    def fark(self, eski, yeni):
        # motor.yaz() farkı tam olarak böyle üretir
        return "".join(difflib.unified_diff(eski.splitlines(keepends=True),
                                            yeni.splitlines(keepends=True),
                                            fromfile="x (eski aaaaaaaa)",
                                            tofile="x (yeni bbbbbbbb)", n=3))

    def test_ters_uygulama_eski_nushayi_verir(self):
        self.assertEqual(dg.geri_kur(self.YENI, self.fark(self.ESKI, self.YENI)), self.ESKI)

    def test_yanlis_nushaya_uygulanamaz(self):
        with self.assertRaises(ValueError):
            dg.geri_kur(self.YENI.replace("Son", "SON"), self.fark(self.ESKI, self.YENI))

    def test_fark_basligi(self):
        self.assertEqual(dg._fark_basligi(self.fark(self.ESKI, self.YENI)),
                         ("aaaaaaaa", "bbbbbbbb"))


class MaddeVeBloklar(unittest.TestCase):
    METIN = ("Amaç\n MADDE 1- (1) Bu Yönetmeliğin amacı test etmektir ve yeterince uzundur.\n"
             "Kapsam\n MADDE 2- (1) Kapsam fıkrası.\n"
             " (2) İkinci fıkra da test için yeterince uzun bir cümledir.\n MADDE 3- Yürürlük.\n")

    def test_madde_metni(self):
        m2 = dg.madde_metni(self.METIN, "2")
        self.assertTrue(m2.lstrip().startswith("MADDE 2-"))   # girinti korunur
        self.assertIn("(2) İkinci fıkra da test", m2)
        self.assertNotIn("MADDE 3", m2)
        self.assertIsNone(dg.madde_metni(self.METIN, "9"))

    def test_bloklar_aralik_disinda_icerikle_bulunur(self):
        """Geçiş farkında satır numaraları kayık: blok, maddenin metnindeki
        satırı taşıdığı için yine bulunmalı."""
        fark = ("--- x\n+++ x\n@@ -50,2 +50,2 @@\n"
                " (2) İkinci fıkra da test için yeterince uzun bir cümledir.\n"
                "-eski\n+yeni\n"
                "@@ -90,1 +90,1 @@\n-alakasız\n+başka\n")
        m2 = dg.madde_metni(self.METIN, "2")
        bloklar = dg.ilgili_bloklar(fark, 3, 6, m2)
        self.assertEqual(len(bloklar), 1)
        self.assertIn("-eski", bloklar[0])
        self.assertEqual(len(dg.ilgili_bloklar(fark, 89, 92)), 1)   # aralık ölçütü


class AymOzeti(unittest.TestCase):
    """Hüküm fıkrasının OCR metninden sonuç okuma. Örnekler 17–21.09.2026
    kararlarının GERÇEK OCR çıktısından alındı (bozuklukları dahil)."""

    def test_bireysel_iddia_cumlesi_ihlal_sayilmaz(self):
        # küçük harfli "ihlal edildiğine ilişkin iddia" SONUÇ değildir
        m = ("I. BAŞVURUNUN ÖZETİ\n1. Başvuru, ifade özgürlüğünün ihlal edildiği iddiasına ilişkindir.\n"
             "IV. HÜKÜM\nAçıklanan gerekçelerle;\nA. İfade özgürlüğünün ihlal edildiğine ilişkin "
             "iddianın KABUL EDİLEBİLİR OLDUĞUNA,\nB. Anayasa'nın 26. maddesinde güvence altına "
             "alınan ifade özgürlüğünün İHLAL EDİLMEDİĞİNE,\n")
        konu, sonuc = dg.aym_ozeti(m, "bireysel")
        self.assertEqual(sonuc, "İHLAL YOK")
        self.assertTrue(konu.startswith("ifade özgürlüğünün"))

    def test_ocr_harf_bozukluklari(self):
        m = ("IV. HÜKÜM\nkapsamındak i gazykşei karar akmın iHLAL EDİLDiĞiNE,\n"
             "2. Diğer ihlal iddiasının KABUL EDİLEMEZ OLDUGUNA,\nBaşkan | Üye\n")
        self.assertEqual(dg.aym_ozeti(m, "bireysel")[1],
                         "İHLAL VAR · bir kısım iddia KABUL EDİLEMEZ")

    def test_norm_konu_hukum_kelimesinde_kesilir(self):
        m = ("VI. HÜKÜM\n4/12/2004 tarihli ve 5271 sayılı Ceza Muhakemesi Kanunu'nun 283. "
             "maddesinin Anayasa'ya aykırı olmadığına ve itirazın REDDINE, Kadir ÖZKAYA ile "
             "Engin YILDIRIM'ın karşıoyları ve OYÇOKLUĞUYLA karar verildi.\n")
        konu, sonuc = dg.aym_ozeti(m, "norm")
        self.assertEqual(sonuc, "RET")
        self.assertTrue(konu.endswith("REDDINE"))

    def test_norm_tablo_ayraci_ve_kvyo(self):
        m = "VI. HÜKÜM\n… ibaresine ilişkin itiraz başvurusu hakkında | KARAR VERİLMESİNE | YER OLMADIĞINA\n"
        self.assertEqual(dg.aym_ozeti(m, "norm")[1], "KARAR VERİLMESİNE YER YOK")

    def test_ayrisik_unicode(self):
        import unicodedata
        m = unicodedata.normalize("NFD", "IV. HÜKÜM\nhakkının İHLAL EDİLDİĞİNE,\n")
        self.assertEqual(dg.aym_ozeti(m, "bireysel")[1], "İHLAL VAR")


class AymIsaretleri(unittest.TestCase):
    """Tablo işaretleri (kullanıcı kararı 26.09.2026)."""

    def test_sonuc_isareti_bastaki_sonuca_gore(self):
        self.assertEqual(dg.sonuc_isareti("İHLAL VAR · bir kısım iddia KABUL EDİLEMEZ"), "❗")
        self.assertEqual(dg.sonuc_isareti("İHLAL YOK · bir kısım iddia KABUL EDİLEMEZ"), "✖️")
        self.assertEqual(dg.sonuc_isareti("KISMEN · İPTAL · RET"), "❗")
        self.assertEqual(dg.sonuc_isareti("RET"), "✖️")
        self.assertEqual(dg.sonuc_isareti("KARAR VERİLMESİNE YER YOK"), "➖")
        self.assertEqual(dg.sonuc_isareti("hüküm okunamadı"), "❔")

    def test_saglik_konu_cumlesinden(self):
        self.assertTrue(dg.saglik_mi("tıbbi ihmal ve organizasyon kusuru sonucu bir bebeğin "
                                     "ölü olarak doğmasıyla ilgili tazminat davası"))
        self.assertTrue(dg.saglik_mi("özel hastanede hekimin sözleşmesinin feshi"))
        self.assertFalse(dg.saglik_mi("ceza infaz kurumunda süreli yayına erişim talebinin reddi"))
        self.assertFalse(dg.saglik_mi("hayvan sağlığı mevzuatına aykırılık"))   # GÜRÜLTÜ


class EtkiSuzgeci(unittest.TestCase):

    def test_belge_adi_ya_da_kanun_no(self):
        ohy = dg._belge_isaretleri({"ad": "Özel Hastaneler Yönetmeliği", "tur": "KurumVeKurulusYonetmeligi"})
        self.assertTrue(ohy.search(dg.c.tr_kucult("ÖZEL HASTANELER Yönetmeliği m.24/2")))
        self.assertFalse(ohy.search(dg.c.tr_kucult("KMK m. 24 uyarınca")))
        kmk = dg._belge_isaretleri({"ad": "Kat Mülkiyeti Kanunu", "tur": "Kanun", "no": "634"})
        self.assertTrue(kmk.search("634 sayılı kanun m.12"))
        self.assertFalse(kmk.search("6340 sayılı"))


if __name__ == "__main__":
    unittest.main()
