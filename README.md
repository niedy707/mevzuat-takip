# mevzuat — güncellik takibi

**mevzuat.gov.tr**'deki kanun ve yönetmeliklerin güncelliğini izler ve bir şey
değiştiğinde **ne değiştiğini madde madde** söyler.

> **Altın kural:** Hukuk metninin tek kaynağı `mevzuat.gov.tr`'dir. Bir belgeye madde
> numarası, oran, süre ya da nisap yazılacaksa **önce lafzı okunur.** Metne
> ulaşılamıyorsa uydurulmaz — "ulaşamadım" denir.

**Arayüz:** http://127.0.0.1:3031 · **İzlenen:** 51 mevzuat · **Envanter:** ~4.800 madde

---

## Neden var

Metin hash'i yalnız *"bir şey değişti"* der. Bu proje *"**ne** değişti"* der:

| Olay | Şiddet |
|---|---|
| **Yürütmesi durduruldu** (Danıştay) | 🔴 kritik |
| **Yürütme durdurma kalktı** | 🔴 kritik |
| **Anayasa Mahkemesi'nce iptal** | 🔴 kritik |
| Madde mülga edildi / metinden kaldırıldı | 🔴 kritik |
| Kritik madde metni değişti | 🔴 kritik |
| Madde eklendi / madde metni değişti | 🟡 önemli |
| Metin değişti ama madde envanteri aynı | ⚪ bilgi |

**Bildirim (26.09.2026'dan beri):**

| Ne | Ne zaman | Bildirim |
|---|---|---|
| **Günlük özet** | her gün 09:00 (`com.mevzuat.gunluk`) | **Her gün gider** — değişiklik yoksa "değişiklik yok" der (= sistem çalıştı). Dokununca özet sayfası açılır |
| **Acil bildirim** | 07·10·13·16·19·22 (`com.mevzuat.acil`) | Yalnız **acil listesindeki** belgelerde kritik/önemli değişiklik, onları anan RG kaydı ya da RG'de "yürütmenin durdurulması" görülünce — günlüğü beklemeden, ayrı sayfayla (`timeSensitive`). Liste arayüzden seçilir: **Mevzuat** sekmesi → kartta **🚨 acil** düğmesi (`acil-secim.json`; yoksa varsayılan 19 çekirdek belge) |

Sayfalar: **https://mevzuat-ozet.vercel.app** (public, `noindex`) — her değişiklikte eski/yeni lafız,
kelime farkı ve **mevzuat.gov.tr linki**; RG kayıtlarında Resmî Gazete linki; AYM tablosu (🩺 ❗ ✖️).
`kaynak.json` `neden` alanları ve etki taraması **yayımlanmaz** (dava gerekçesi).

**Şu an canlı tespit edilen:** 12 maddenin yürütmesi durdurulmuş durumda
(`y-ayakta-teshis` 6 · `y-ozel-hastaneler` 3 · diğerleri), 46 madde AYM'ce iptal edilmiş.

---

## Günlük kullanım

```bash
cd ~/Projects/mevzuat
```

| Komut | Ne yapar |
|---|---|
| `python3 mevzuat.py madde 4857-is-kanunu 17` | ★ **Maddenin LAFZINI basar.** Alıntı yapmadan önce çalıştırılır |
| `python3 mevzuat.py denetle` | ★ **Güncellik denetimi** — 51 kaydı çeker, değişeni madde madde bildirir |
| `python3 mevzuat.py rg 7` | ★ **Resmî Gazete taraması** — değişikliği yayım günü yakalar |
| `python3 mevzuat.py bul "kıdem tazminatı"` | Külliyatta tam metin arama (sonuç madde numarasıyla) |
| `python3 mevzuat.py fark <slug> --kelime` | Son değişikliğin **kelime düzeyinde** farkı |
| `python3 mevzuat.py olaylar --kritik` | Değişiklik günlüğü |
| `python3 mevzuat.py degisiklikler` | ★ **Numaralı değişiklik raporu** — son rapordan beri gelenlerin hepsi + önceki 10; madde olayları ve Resmî Gazete tek listede, **AYM kararları ayrı grupta konu/sonuç özetiyle**. Claude'da: `/degisiklikler` (bayatlayan belgelere onaylı, tarihli not düşer) |
| `python3 mevzuat.py degisiklik 5` | 5 numaranın detay paketi: eski/yeni lafız, kelime farkı, atıf yapan belgeler, RG metni |
| `python3 yayin.py onizle` | Günlük özet sayfasını yalnız üret (`yayin/`), yayınlama/bildirim yok |
| `python3 yayin.py gunluk [--gonderme]` | Günlük özeti üret → Vercel → canlıda doğrula → Bark (günlük işin 3. adımı) |
| `python3 acil_is.py [--deneme]` | Çekirdek belgelerin acil kontrolü; `--deneme` zinciri "🧪 DENEME" bildirimiyle sınar |
| `python3 mevzuat.py etki 4857-is-kanunu 17` | Bu maddeye atıf yapan belgelerim hangileri |
| `python3 mevzuat.py liste` | İzlenen 51 mevzuatın tablosu |
| `python3 mevzuat.py durum` | Sistem sağlığı |
| `python3 mevzuat.py ara "Uzaktan Çalışma" Yonetmelik` | Yeni kayıt eklerken numarayı **çöz** — tahmin etme |
| `npm run sunucu` | Arayüzü başlat (`:3031`) |

Tam denetim ~3,5 dakika (51 kayıt, sıralı çekim, istekler arası 1,5 sn).
Statik kanunlarda koşullu GET sayesinde değişmemiş belge **hiç indirilmez**.

---

## İki bağımsız sinyal

```
┌─ 1. mevzuat.gov.tr ────────────────┐   ┌─ 2. Resmî Gazete ──────────────┐
│  konsolide metin                   │   │  günlük fihrist (JSON API)     │
│  PDF/metin hash'i + madde envanteri│   │  değişikliğin YAYIM GÜNÜ        │
│  → NE değişti (madde düzeyinde)    │   │  → değişiklik OLDU (aynı gün)  │
│  gecikme: gün(ler)                 │   │  gecikme: yok                  │
└────────────────────────────────────┘   └────────────────────────────────┘
                     └────────► gunluk.json ◄────────┘
                                    │
                         arayüz :3031  +  Bark bildirimi
```

**Neden ikisi birden:** mevzuat.gov.tr yalnız *konsolide* metni sunar ve konsolidasyon
Resmî Gazete yayımından gün(ler) sonra yapılır. RG tarafı "bugün bir şey yayımlandı"
der ama madde farkını veremez; mevzuat.gov.tr tarafı madde farkını verir ama geç kalır.

**RG süzgeci:** izlenen 51 belge · sağlık mevzuatı · Anayasa Mahkemesi ve Danıştay
kararları · "yürütmenin durdurulması" ibaresi · **EPDK Kurul Kararları**.
**İlân bölümü elenir.**

---

## Dosyalar

| | |
|---|---|
| `kaynak.json` | ★ **TEK KAYNAK** — hangi mevzuat izleniyor, sınıfı, kritik maddeleri. Elle düzenlenir |
| `kaynak-notlar.json` | **git DIŞI** — kişisel `neden` notları + taranacak proje kökleri. Yoksa araç yine çalışır |
| `durum.json` | **ÜRETİLİR** — imza, madde envanteri, son doğrulama. Elle düzenlenmez |
| `gunluk.json` | **ÜRETİLİR** — değişiklik olayları (arayüz bunu okur) |
| `metin/*.txt` | ★ Çıkarılmış metin — **sürüm denetiminde**, `git diff` değişikliği burada gösterir |
| `pdf/*.pdf` | Orijinal PDF — `.gitignore`'da (yeniden indirilebilir) |
| `arsiv/*_fark.diff` | ★ Değişiklik anındaki satır farkı — **sürüm denetiminde** |
| `kayit/rapor-durum.json` | **ÜRETİLİR** — değişiklik raporunun "son rapor" işareti ve numara eşlemesi (git dışı) |
| `kayit/rg-belge/` | Resmî Gazete belge önbelleği: PDF + metin/OCR kopyası (git dışı) |
| `yayin/` | **ÜRETİLİR** — public statik site (git dışı); `yayin/.vercel/project.json` Vercel bağlantısı |
| `kayit/yayin-durum.json` | Hangi kayıt hangi günlük özette yayımlandı / acil bildirildi, sayfa arşivi |
| `kayit/acil-nabiz.json` | Acil işin son 60 koşusu — günlük sayfa "acil kontrol: son koşu" diye gösterir |
| `com.mevzuat.acil.plist` | Acil işin launchd tanımı (`~/Library/LaunchAgents`'a kopyalanır) |
| `acil-secim.json` | ★ Acil bildirim kapsamındaki belgeler — arayüzden değiştirilir; silinirse varsayılan: çekirdek sınıfı |
| `sertifika/mevzuat-ca.pem` | TLS doğrulaması için CA bundle (`kur.sh` üretir, git dışı) |

### Modüller

| | |
|---|---|
| `cekirdek.py` | indirme katmanı: doğrulanmış TLS · nezaket · hibrit adres çözümü |
| `analiz.py` | ★ madde envanteri ve olay üretimi — projenin ayırt edici parçası |
| `motor.py` | denetim çekirdeği: çek · karşılaştır · devre kesici |
| `mevzuat.py` | CLI |
| `rg.py` | Resmî Gazete ikinci sinyali |
| `sunucu.py` | arayüz sunucusu (`:3031`, yalnız 127.0.0.1) |
| `bildirim.py` | Bark köprüsü |
| `etki.py` | "bu madde değişti, hangi belgemi etkiler" |
| `degisiklik.py` | ★ değişiklik raporu: madde olayları + RG kayıtları tek zaman çizelgesinde, numaralı; `/degisiklikler` skill'inin motoru |
| `danistay.py` | Danıştay karar araması (elle araştırma — erken uyarı kanalı **değil**) |
| `paylasim.py` | ★ **Kardeş projelerin kullandığı salt okunur arayüz** (is-hukuku · 5levent) |
| `gunluk_is.py` | launchd günlük koşusu (RG + denetim + günlük özet sayfası + bildirim) |
| `yayin.py` | ★ public özet/acil sayfaları: üret · `vercel deploy` · canlıda doğrula · Bark (linkli) |
| `acil_is.py` | gün içi acil kontrol (19 çekirdek belge + RG) → acil sayfa + bildirim |

---

## Bilinmesi gerekenler

**1 · Tespit hibrittir.** Kanun/KHK statik dosyadır: bayt hash'i + `If-None-Match`
koşullu GET (HTTP 304). Yönetmelik `GeneratePdf` ile anlık üretilir, her indirmede
farklı bayt verir → orada normalize **metin** hash'i esastır. (21 statik / 24 üretilen.)

**2 · Devre kesici.** Tek koşuda külliyatın **%20'sinden fazlası** değişmiş görünürse
hiçbir dosya güncellenmez ve bildirim gitmez. Sebep neredeyse her zaman `pdftotext`
sürüm değişikliğidir — gerçek mevzuat değişikliği külliyatın beşte birini aynı gün
değiştirmez. `durum.json`'a araç sürümü damgalanır.

**3 · TLS doğrulanır, `-k` kullanılmaz.** Sunucu ara sertifikayı göndermiyor;
`sertifika/kur.sh` onu AIA'dan çekip bundle yapar. ⚠️ Motor `curl` değil Python `ssl`
kullanır — Apple curl'ü yanlış CA ile de başarılı oluyor (bkz. `COZUMLER.md`).

**4 · HTTP 200 başarı demek değildir.** Sunucu yığın isteği kısıtlarken 200 ile HTML
hata sayfası döndürür. Üç kapı: `%PDF-` sihirli baytı · içerik anahtarı · metin
yarıdan fazla kısalmamış olması. Biri düşerse depodaki nüshaya **dokunulmaz.**

**5 · Belirsizlik sessiz kalmaz.** Ayrıştırıcı bir maddeyi kesin eşleştiremezse
(mükerrer anahtar) bu sayılır ve arayüzde `⚠ belirsiz` rozetiyle gösterilir.

**6 · Bu proje ekosistemin TEK mevzuat kaynağıdır (19.09.2026'dan beri).**
`is-hukuku/mevzuat/mevzuat.py` artık buraya **köprü**dür (komutları iletir);
`5levent/araclar/mevzuat-sync.py` metni buradan **okur** ve yalnız siteye mobil
HTML üretir. İkisi de kendi indirmesini yapmaz. Kardeş projeler `paylasim.py`
arayüzünü kullanır:

```python
import sys; sys.path.insert(0, "../mevzuat")
import paylasim
metin = paylasim.metin("634-kat-mulkiyeti")
m20   = paylasim.madde("634-kat-mulkiyeti", "20")
```

⚠️ Kardeş klasör bağımlılığı: `~/Projects/mevzuat` tek başına taşınırsa iki proje
de sessizce kırılır (ekosistemin bilinen tuzağı — kök `INFRASTRUCTURE.md`).

---

## Otomatik koşu

`.plist` dosyalarında yol `__PROJE_YOLU__` yer tutucusudur — kurarken kendi
yolunla değiştir:

```bash
for f in com.mevzuat.gunluk.plist com.mevzuat.acil.plist; do
  sed "s#__PROJE_YOLU__#$PWD#g" "$f" > ~/Library/LaunchAgents/"$f"
  launchctl load ~/Library/LaunchAgents/"$f"
done
```

Her gün **09:00**: Resmî Gazete taraması → güncellik denetimi → Bark bildirimi.
Kayıt: `kayit/gunluk.log`.

## Test

```bash
npm test          # 42 test — ayrıştırıcı, RG süzgeci, kelime farkı, hibrit tespit
```

Her test 19.09.2026'da gerçek külliyatta **ölçülmüş** bir tuzağa karşılık gelir.
Ayrıntılar: [`COZUMLER.md`](COZUMLER.md).
