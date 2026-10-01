# CLAUDE.md — mevzuat

Bu dosya `~/Projects/mevzuat` içinde çalışırken geçerlidir. Kök
`~/Projects/CLAUDE.md` de geçerlidir; çakışma olursa **bu dosya önceliklidir.**

---

## Bu proje ne yapar

mevzuat.gov.tr'deki 51 kanun/yönetmeliğin güncelliğini izler ve değişince
**madde düzeyinde olay** üretir: eklenen/kaldırılan madde, mülga, Anayasa
Mahkemesi iptali, **yürütmenin durdurulması** ve **durdurmanın kalkması**.
İkinci bağımsız sinyal Resmî Gazete günlük fihristidir.

---

## ⛔ Asla yapılmayacaklar

- **`durum.json` ve `gunluk.json` ELLE DÜZENLENMEZ.** Üretilen dosyalardır.
  Değişiklik gerekiyorsa `kaynak.json`'a dokunulur ve `denetle` koşulur.
- **`kaynak.json`'a numara TAHMİNLE yazılmaz.** Önce
  `python3 mevzuat.py ara "<ifade>" <tur>` ile doğrulanır. 19.09.2026'da
  `y-yapi-denetimi`'nin numarası bu yüzden yanlıştı (12452 → 11951).
- **`-k` / `verify=False` geri getirilmez.** TLS doğrulaması `sertifika/kur.sh`
  bundle'ı ile yapılır. Bu projenin tek işi resmî metnin doğruluğunu garanti etmek.
- **`pdftotext -raw` ya da varsayılan moda geçilmez.** `-layout` korunur; diğer
  modlar kanun künye tablosunda etiket–değer eşleşmesini bozuyor (ölçüldü).
- **Devre kesici eşiği gevşetilmez.** %20 üzeri kütle değişimi neredeyse her zaman
  araç sürümü değişikliğidir, mevzuat değişikliği değil.
- **`is-hukuku/mevzuat/` ve `5levent/araclar/mevzuat-sync.py` silinmez.**
  İkincisi siteye mobil HTML üretir — işlevi farklıdır.
- **Bark'a `--kritik` gönderilmez** — kullanıcı "beni uyandır" demedikçe. Acil bildirim
  `timeSensitive`'tir, `--kritik` değil.
- **Public sayfaya (`yayin.py` → mevzuat-ozet.vercel.app) `neden`, etki taraması, olay
  `not`/`kaynak` metni ya da iç dosya yolu KONMAZ.** `test/test_yayin.py` bunu sınar.
- **`yayin/` klasörüne `.env*` girmez** — `vercel link` oraya `VERCEL_OIDC_TOKEN` indirir;
  `.vercelignore` dışlar, dosya silinir (bkz. `COZUMLER.md` 26.09.2026).

## Madde alıntısı yapmadan önce — zorunlu

```bash
python3 mevzuat.py madde <slug> <no>       # ör: madde 4857-is-kanunu 17
python3 mevzuat.py madde 193-gelir-vergisi "mükerrer 121"
python3 mevzuat.py madde 4857-is-kanunu "ek 3"
```

Çıktının başında **son doğrulama zamanı** yazar. Bir aydan eskiyse önce `denetle`.

---

## Mimari

```
kaynak.json (TEK KAYNAK, elle)
      │
      ▼
cekirdek.py ── doğrulanmış TLS · nezaket (1,5 sn) · çok adaylı adres
      │
      ▼
  motor.py ── HİBRİT TESPİT
      │         Kanun/KHK  → PDF bayt hash'i + If-None-Match (HTTP 304)
      │         Yönetmelik → normalize METİN hash'i (GeneratePdf bayt-kararsız)
      ▼
 analiz.py ── madde envanteri → OLAY üretimi
      │
      ├──► durum.json   (envanter, imza, son doğrulama)
      └──► gunluk.json  (olaylar) ──► sunucu.py :3031  +  bildirim.py (Bark)

rg.py ── Resmî Gazete günlük fihristi (İKİNCİ BAĞIMSIZ SİNYAL, aynı gün)

yayin.py ── public özet sayfaları → vercel deploy → canlıda doğrula → Bark (linkli)
   ▲ gunluk_is.py (09:00, her gün)      ▲ acil_is.py (07·10·13·16·19·22, acil-secim.json)
```

### Hibrit tespit neden (ÖLÇÜLDÜ 19.09.2026)

| | Statik `1.5.4857.pdf` | `GeneratePdf` yönetmelik |
|---|---|---|
| İki indirme sha256 | **aynı** | **farklı** (üretim damgası gömülü) |
| `ETag` / `Last-Modified` | var | yok |
| Tespit | bayt hash + koşullu GET | normalize metin hash |

---

## Komutlar

```bash
python3 mevzuat.py denetle          # ~3,5 dk · çıkış 0 temiz · 1 olay/hata · 3 devre kesici
python3 mevzuat.py denetle --kuru   # hiçbir dosyaya dokunmadan
python3 mevzuat.py rg 7             # Resmî Gazete son 7 gün
python3 mevzuat.py bul "<ifade>"    # külliyatta arama
python3 mevzuat.py etki <slug> <no> # atıf yapan belgelerim
python3 mevzuat.py degisiklikler   # numaralı rapor: son rapordan beri + önceki 10
python3 mevzuat.py degisiklik <no> # o numaranın detayı (eski/yeni lafız, etki, RG metni)
npm run sunucu                      # arayüz :3031
npm test                            # 78 test
python3 gunluk_is.py                # launchd 09:00: RG + denetim + günlük özet sayfası + Bark (HER GÜN)
python3 acil_is.py [--deneme]       # launchd 07·10·13·16·19·22: acil listesi → ACİL bildirim
                                    # liste: arayüz → Mevzuat → 🚨 acil (acil-secim.json; yoksa çekirdek)
python3 yayin.py onizle             # özet sayfasını yalnız üret (yayin/)
```

**Dosya taşıyan/silen hiçbir komutu `--kuru` görmeden çalıştırma.**

---

## Port

**3031** bu projeye sabittir (`PORTS_REGISTRY.md`'ye işlendi). Yalnız `127.0.0.1`.
Otomatik port ataması kabul edilmez.

## Dil

Tüm dokümantasyon, commit mesajları, arayüz metinleri ve kod yorumları **Türkçe**.

## Gizlilik

⚠️ **Depo PUBLIC'tir (02.10.2026'dan beri).** Kişisel olan her şey git dışındadır:

| Git DIŞI | Neden |
|---|---|
| `kaynak-notlar.json` | ★ `neden` alanları (bir mevzuatın hangi dosya/uyuşmazlık için izlendiği) + `_atif_kokleri` (yerel proje yolları) |
| `gunluk.json` | Olay defteri — `not` alanları iç süreç/sözleşme ayrıntısı taşır |
| `mevzuat_tara*.md/json` | İç geliştirme raporu; özel depoların içeriğini tartışır |
| `sertifika/*.pem` · `pdf/` · `yayin/` · `kayit/` | Makineye özgü / üretilen |

**Yeni `neden` yazarken `kaynak.json`'a DEĞİL `kaynak-notlar.json`'a yaz.**
`cekirdek.kaynak()` ikisini birleştirir; notlar dosyası yoksa araç tam çalışır
(yalnız arayüzde "neden izleniyor" boş kalır, `etki` kök bulamadığını söyler).

Mevzuat metinlerinin kendisi kamuya açıktır (FSEK m. 31) — depoda durmaları sorun değil.

⛔ **Public sayfaya ve depoya girmeyecekler bir arada:** `neden`, etki taraması
sonucu, olay `not`/`kaynak` serbest metni, iç dosya yolu. `test/test_yayin.py`
public sayfa için bunu sınar.

---

## Bir değişiklik çıkarsa

0. **`/degisiklikler`** skill'i (`.claude/skills/degisiklikler/`) aşağıdaki 1–3'ü tek pakette
   yapar: numaralı liste → "5'i detaylandır" → eski/yeni lafız + etki + yorum.
1. `python3 mevzuat.py fark <slug> --kelime` — neyin değiştiğini oku.
2. Değişen madde `kritik_madde` listesinde mi? (arayüzde çerçeveli görünür)
3. `python3 mevzuat.py etki <slug> <madde>` — hangi belgelerim etkilendi.
4. Rakam değiştiyse (tavan, oran, süre) ilgili projenin hesap zincirini koştur.
5. **İmzalı/teslim edilmiş belgeler yeniden basılmaz** — düzeltme yolu zeyilnamedir.

## Tuzaklar

Hepsi ölçülmüştür, ayrıntısı [`COZUMLER.md`](COZUMLER.md)'de:

1. `re.IGNORECASE` Türkçe'de `ı` ile `i`'yi aynı sayar → `cekirdek.tr_kucult()` kullan.
2. `Mükerrer Madde 121` ve `Madde 98/A` ayrı maddelerdir.
3. Kuyruk dizini işareti `İŞLENEMEYEN` (— `HÜKÜM` değil).
4. HTTP 200 başarı demek değil; `%PDF-` kontrolü şart.
5. Apple curl `--cacert`'i yok sayabiliyor → Python `ssl` kullanılır.
6. Dipnotlar madde gövdesine karışıp sahte "değişti" üretir → `dipnot_ayir()`.
