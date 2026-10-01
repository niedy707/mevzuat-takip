# Çözümler defteri — mevzuat

> Test: *"Aynı sorun 3 ay sonra karşıma çıksa, çözümü yeniden bulmam ne kadar sürerdi?"*
> Buradaki girişlerin hepsi **ölçülerek** bulundu; hiçbiri tahmin değildir.

---

## 25.09.2026 — Yönetmeliklerin "son doğrulama" tarihi hiç ilerlemiyordu

**Belirti:** Günlük iş her sabah 51 kaydın hepsini denetliyordu (`kayit/gunluk.log`),
ama `durum.json`'da metin imzalı yönetmeliklerin `son_dogrulama`'sı ilk indirme
gününde kalmıştı (`y-uzaktan-calisma`: 19.09.2026 22:35). Kanunlar doğruydu.
`madde` çıktısı, arayüz ve `degisiklik` detayı bu bayat tarihi gösteriyordu; "bir
aydan eskiyse önce `denetle`" kuralı yüzünden bir ay sonra her yönetmelik alıntısı
gereksiz denetim isteyecekti.

**Kök neden:** Damga yalnız `motor.kalem()`'in **304 dalında** basılıyordu. Yönetmelik
ETag vermediği için hiç 304 almaz; metin hash'iyle "ayni" çıkar — ve `_kos()` yalnız
"ilk" ile "degisti"yi `motor.yaz()`'a gönderiyordu. "ayni" hiçbir yere yazılmıyordu.

**Çözüm:** `kalem()` artık `durum`a hiç dokunmuyor; "ayni" sonucu kontrol anını
`dogrulama_zamani` olarak taşıyor. `_kos()`, devre kesici geçtikten sonra
`motor.dogrulamayi_isle()` ile hem 304'ün hem metin-hash'in damgasını basıyor.
Regresyon testi: `test/test_dogrulama.py`.

**İkinci sızıntı (aynı kökten):** 304 dalı damgayı bellekteki `durum`a doğrudan
basıyordu. Aynı koşuda bir "ilk" indirme olursa artımlı kayıt (`c.kaydet` döngü içinde)
bu damgayı **devre kesiciden önce** diske yazıyordu — kesici "hiçbir dosya güncellenmedi"
derken 304'lü kayıtlar "doğrulandı" görünüyordu. Test bunu da yakalıyor.

**Neden bariz olan işe yaramadı:** "ayni" için de `motor.yaz()`'ı çağırmak — `yaz()`
metin dosyasını yeniden yazar ve `durum` kaydını baştan kurar (ör. `arac_surumu`'nu o
anki sürüme çeker); değişmemiş kayıt için gereksiz yan etki. Damgayı `kalem()` içinde
metin dalına da eklemek — 304 dalındaki sızıntıyı yönetmeliklere de taşırdı.

## 26.09.2026 — `vercel link` klasöre gizli belirteç indiriyor; public statik yayında sızardı

**Belirti:** Yayın klasörü (`yayin/`) `vercel link --project mevzuat-ozet` ile bağlandı; komut
sessizce `.env.local` yazdı: `VERCEL_OIDC_TOKEN=…`. Klasör **public** bir statik site olarak
yükleniyor.

**Kök neden:** Vercel CLI `link` sırasında projenin geliştirme ortam değişkenlerini "kolaylık"
olarak indiriyor (çıktıda yalnız `✓ Created .env.local file and added it to .gitignore` yazıyor).
`.gitignore`'a eklenmesi git'i korur, **deploy'u korumaz** — deploy `.gitignore`'a değil
`.vercelignore`'a bakar.

**Çözüm:** Dosya silindi; `yayin/.vercelignore` → `.env*`, `.vercel`, `*.py`. Yayın klasörü
depodan ayrı tutuldu: depo Vercel'e bağlı değil, yüklenen tek şey `yayin.py`'nin ürettiği HTML.

**Neden bariz olan işe yaramadı:** "Varsayılan ignore listesi `.env.local`'i zaten dışlıyordur"
varsayımına güvenilmedi — sınanmadan gizli bir belirteci public klasörde bırakmanın maliyeti
yüksek. Dış bağlantıyı `vercel link` yerine elle `project.json` yazarak kurmak da mümkündü ama
`orgId` gerektiriyor; bağla-sonra-temizle daha az kırılgan.

---

## 26.09.2026 — Günlük bildirim yalnız olay olunca gidiyordu; sessizlik "çalışmıyor" ile karışıyordu

**Belirti:** 19.09'dan beri günlük iş olay yoksa bildirim göndermiyordu; mesajdaki link
`http://127.0.0.1:3031/gunluk` telefondan açılmıyordu. İş ekosistemin zamanlayıcı tablosunda da yoktu.

**Çözüm (kullanıcı kararı):** Bildirim **her gün** gider ("değişiklik yok" = "sistem çalıştı");
link public özet sayfasıdır. Yayın `200 OK` ile değil, sayfaya gömülen **yayın kimliğinin**
canlıda okunmasıyla doğrulanır (`yayin.dogrula`) — eski sürüm de 200 döner. Doğrulanmazsa kayıtlar
"yayımlandı" sayılmaz, ertesi günün özetine yeniden girer. Acil iş sessiz kalabildiği için her
koşusunu `kayit/acil-nabiz.json`'a yazar; günlük sayfa bunu gösterir, 16 saat koşmazsa uyarır.

---

## 25.09.2026 — RG belge sayfaları TLS'te düşüyor (`www.` ≠ `api.`)

**Belirti:** `degisiklik.py` RG kaydının metnini açarken
`CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`. Oysa `rg.py`
aylardır aynı alan adından fihrist çekiyordu.

**Kök neden:** İki ayrı sunucu. `api.resmigazete.gov.tr` zinciri **tam** gönderiyor
(leaf + GeoTrust ara + kök, `Verify return code: 0`). Belgelerin durduğu
`www.resmigazete.gov.tr` ise mevzuat.gov.tr ile **aynı** `CN=*.tccb.gov.tr` sertifikasını
ve **aynı eksik zinciri** sunuyor (yalnız leaf, `Verify return code: 21`).

**Çözüm:** Yeni bundle gerekmedi — `sertifika/mevzuat-ca.pem` (GeoTrust TLS RSA CA G1 +
DigiCert Global Root G2) bu sunucuyu da doğruluyor. `rg_belge_metni()` → `context=c.baglam()`.

**Neden bariz olan işe yaramadı:** `-k`/`verify=False` bu projede yasak. "rg.py çalışıyor,
demek ki RG'nin TLS'i sağlam" varsayımı yanlıştı — `rg.py` hiç `www.`'ye gitmiyordu.

---

## 25.09.2026 — AYM/EPDK kararlarının PDF'inden metin çıkmıyor; OCR da atlanıyordu

**Belirti:** RG'deki Anayasa Mahkemesi kararlarında `pdftotext -layout` yalnız boşluk
döndürdü. `pdf-md.sh` ile OCR'a verildiğinde de **ilk sayfa** (künye, itiraz konusu) boş
kaldı; kalan sayfalar OCR'landı.

**Kök neden:** PDF'ler QuarkXPress çıktısı ve fontlarında Unicode eşlemesi yok
(`pdffonts`: `uni no`). `pdftotext` harf yerine **glif kimliklerini kontrol baytı** olarak
basıyor (`\x01`–`\x17`). Bu baytlar boşluk sayılmadığı için hem `re.sub(r"\s", …)` hem
`tr -d '[:space:]'` sayfayı "metin var" sandı (ilk sayfa: 115 "karakter").

**Çözüm:** `degisiklik.py` metin katmanını **harf** sayarak yargılar
(`[^\W\d_]` < 200 → OCR). Global `_global-scripts/pdf-md/pdf-md.sh:73` sayımdan
`[:cntrl:]`'ü de düşüyor (`LC_ALL=C tr -d '[:space:][:cntrl:]'`). Sonuç `kayit/rg-belge/`'de
önbelleğe alınır; aynı karar ikinci kez OCR'lanmaz.

**Neden bariz olan işe yaramadı:** "Boşluk dışı karakter sayısı" eşiği metin katmanı
*hiç olmayan* taranmış sayfayı yakalar, *bozuk* metin katmanını yakalamaz. OCR metni sayı
ve özel adda hata yapar (ölçüldü: "Şanlıurfa" → "Şanhurfa") — alıntıdan önce doğrulanır.

---

## 20.09.2026 — RG fihristi EPDK Kurul Kararının KONUSUNU hiç yazmıyor

**Belirti:** `fatura` projesi için elektrik abonelik rejimini izleyecek bir süzgeç yazıldı:
`son kaynak|serbest tüketici|tarife tablo|kademeli tarife|…`. Gerçek fihriste karşı koşuldu,
**hiçbir kaydı yakalamadı** — oysa aranan üç kararın üçü de o fihristlerdeydi.

**Kök neden:** Resmî Gazete günlük fihristi EPDK kararlarını konusuyla değil, **yalnız
numarasıyla** listeliyor:

```
[KURUL KARARLARI] Enerji Piyasası Düzenleme Kurulunun 30/10/2025 Tarihli ve 13912 Sayılı Kararı
```

Bu karar, mesken son kaynak eşiğini 2026 için 4.000 kWh/yıl'a indiren karardır; konu ancak
kararın PDF'i açılınca görünüyor. Konu anahtarıyla süzmek **yapısal olarak imkânsız.**

**Çözüm:** `rg.EPDK_KARAR` konuya değil **kuruma** bakar (`enerji piyasası düzenleme kurulu`).
180 günlük gerçek fihrist (2.079 kayıt) üzerinde ölçüldü → **ayda ortalama 4,0 kayıt**.
Bu hacim "kritik" şiddetini taşımaz, `onemli`de bırakıldı. Eşik kararlarının çıktığı
**Ekim–Ocak** penceresinde (`rg.ESIK_PENCERESI`) sebep metni "EŞİK PENCERESİ … AÇ" der.

**Neden bariz olan işe yaramadı:** EPDK'nın kendi sitesindeki tablo konuyu yazıyor
(*"…Tebliğ'in 5 inci ve 6 ncı maddelerinde yer alan tüketim miktarına…"*), bu yüzden
fihristin de yazdığı varsayılıyor. Yazmıyor. **Desen yazmadan önce gerçek fihrist çekilip
bakılmalıydı** — ölçmeden yazılan bir süzgeç sessizce hiçbir şey yakalamaz ve bu, gürültü
yapan bir süzgeçten çok daha tehlikelidir: sistem çalışıyor görünür.

**İlgili:** Bu kararlar mevzuat.gov.tr'de **yayımlanmaz**, bu yüzden madde envanteri motoruyla
izlenemez; `kaynak.json` → `_kapsam_disi` altına gerekçesiyle yazıldı.

---

## 19.09.2026 — `re.IGNORECASE` Türkçe'de `ı` ile `i`'yi aynı sayıyor

**Belirti:** Resmî Gazete sağlık süzgeci, *"Motorlu Araçlar … **Tip Onayı** ve Piyasa
Gözetimi Hakkında Yönetmelik"* kaydını "sağlık mevzuatı" diye işaretledi.

**Kök neden:** Süzgeçte `tıp ` deseni `re.IGNORECASE` ile aranıyordu. Python'un
Unicode katlaması `ı` (U+0131) ve `i` harflerinin **ikisini de** `I`'ya katlar;
dolayısıyla büyük/küçük duyarsız eşleştirmede `ı` ile `i` **birbiriyle eşleşir**.
`tıp` deseni `Tip`'i yakalar.

**Çözüm:** `IGNORECASE` kullanılmaz. Metin Türkçe kurallarına göre küçültülür ve
desenler küçük harfle, **büyük/küçük duyarlı** eşleştirilir — `cekirdek.tr_kucult()`:

```python
def tr_kucult(s):
    return s.replace("I", "ı").replace("İ", "i").lower()
```

**Neden bariz olan işe yaramadı:** `str.lower()` tek başına da yetmez — `"I".lower()`
Python'da `"i"` verir (Türkçe'de `"ı"` olmalı) ve `"İ".lower()` birleşik nokta
bırakır (`i̇`). Değiştirme sırası da önemlidir: önce `I→ı`, sonra `İ→i`.

**Test:** `test/test_rg.py::TurkceKucultme`.

---

## 19.09.2026 — "Mükerrer Madde 121" ve "Madde 98/A" ayrı maddelerdir

**Belirti:** Gelir Vergisi Kanunu'nda madde envanteri 13 "mükerrer anahtar" raporladı;
bazı maddeler envanterden sessizce düştü.

**Kök neden:** Ayrıştırıcı yalnız `(Ek|Geçici)` ön eklerini ve düz sayıyı tanıyordu.
Oysa Türk vergi mevzuatında:
- **`Mükerrer Madde 121`**, `Madde 121`'den **tamamen ayrı** bir maddedir (193'te 48 kez geçer).
- **`Madde 98/A`** da `Madde 98`'den ayrıdır. Külliyatta `13/A`, `17/A`, `17/B`,
  `18/A`, `18/B`, `22/A`, `24/A`, `183/A`, `Mükerrer 20/A–D` yaygındır.

İkisi de yakalanmayınca farklı maddeler aynı anahtara düşüyor, ilki kalıp ikincisi atılıyordu.

**Çözüm:** `analiz.MADDE` deseni `Mükerrer` ön ekini ve `/<harf>` son ekini yakalar;
anahtar `"Mükerrer 20/A"` biçiminde üretilir.

**Neden bariz olan işe yaramadı:** Sorun hata vermiyordu — envanter *makul* görünüyordu.
Yalnız mükerrer sayacı raporlandığı için fark edildi. **Ö-4'ün ("belirsizlik sessizce
yutulmasın") gerekçesi budur.**

---

## 19.09.2026 — Kuyruk dizini işareti "İŞLENEMEYEN HÜKÜM" değil

**Belirti:** 193 sayılı Kanunda `Geçici Madde 1` beş ayrı satırda göründü.

**Kök neden:** Kanun metinlerinin sonunda, o kanunu **değiştiren** kanunların kendi
geçici maddelerinin tekrar basıldığı bir bölüm var. Başlık şu biçimde:

```
31/12/1960 TARİH VE 193 SAYILI KANUNA
İŞLENEMEYEN GEÇİCİ MADDELER:
```

Kesim işareti olarak `İŞLENEMEYEN HÜKÜM` aranıyordu — o ifade metinde **geçmiyor**.
Kesim geç yapılınca değiştiren kanunların geçici maddeleri gövdeye karışıyordu.

**Çözüm:** `analiz.KUYRUK` deseninde yalnız `İŞLENEMEYEN` aranır. Külliyattaki 8 kanun
metninde bu bölüm var.

---

## 19.09.2026 — Aynı adres bir seferde PDF, bir seferde HTML döndürüyor

**Belirti:** 11 adresi 2 sn aralıkla arka arkaya çekerken `y-merkezi-isitma` ve
`y-yapi-denetimi` "PDF değil" hatası verdi. Aynı adres tek başına denendiğinde
**5/5 başarılı** oldu.

**Kök neden:** mevzuat.gov.tr yığın isteği kısıtlıyor ve kısıtlarken **HTTP 200** ile
bir HTML hata sayfası döndürüyor. Yani HTTP kodu başarıyı göstermiyor.

**Çözüm:** Üç kapı birden:
1. İstekler arası en az 1,5 sn (`cekirdek.NEZAKET`).
2. `%PDF-` sihirli baytı kontrolü — HTTP 200 yetmez.
3. Geri çekilmeli yeniden deneme (6 → 18 → 45 sn).

Ayrıca başarısız çekim **asla "değişti" sayılmaz** ve depodaki nüshaya dokunulmaz;
aksi hâlde tek bir ağ hatası bir kanunun yürürlükten kalktığı izlenimi verirdi.

---

## 19.09.2026 — Tespit hibrittir: statik PDF bayt, üretilen PDF metin

**Belirti:** Bir araştırma bulgusu "tespiti PDF baytına taşı, poppler zincirden çıksın"
diyordu; başka bir ölçüm ise PDF baytının kararsız olduğunu gösteriyordu. İkisi çelişiyordu.

**Kök neden:** İkisi **farklı altkümeyi** ölçmüş. Ölçtüm:

| | Statik `MevzuatMetin/1.5.4857.pdf` | Üretilen `File/GeneratePdf` |
|---|---|---|
| İki indirme sha256 | `cd75c7fe…` = `cd75c7fe…` **aynı** | `bd139070…` ≠ `d5c97c46…` **farklı** |
| `ETag` | `"1dcdb8a09200693"` ✅ | **yok** |
| `Last-Modified` | `Mon, 04 May 2026` ✅ | **yok** |

Kanun ve KHK statik dosyadır; yönetmelik `GeneratePdf` ile **anlık üretilir** ve
içine üretim damgası gömülür — aynı boyutta bile farklı hash çıkar.

**Çözüm:** `motor.py` hibrit çalışır — Kanun/KHK'da bayt hash'i + `If-None-Match`
koşullu GET (**HTTP 304 alınıyor, doğrulandı**: değişmemiş belge hiç indirilmiyor),
yönetmelikte normalize metin hash'i. Dağılım: 21 statik / 24 üretilen.

**Neden bariz olan işe yaramadı:** Tek bir belgeyle test etmek yanıltıcıydı. Hangi
belgeyi seçtiğine göre iki zıt sonuca varılabiliyordu.

---

## 19.09.2026 — TLS: `--cacert` Apple curl'de gerçek güvence vermiyor

**Belirti:** `-k` yerine doğru CA bundle'ı kurduktan sonra, **yanlış** bir CA ile de
`curl` başarılı oldu (exit 0). Yani doğrulama yapıldığı sanılıyordu ama yapılmıyordu.

**Kök neden:** Bu Mac'teki curl Apple'ın SecureTransport'unu kullanıyor; macOS güven
değerlendirmesi araya giriyor ve eksik ara sertifikayı AIA'dan kendi çekiyor.
`--cacert` bu yolda belirleyici olmuyor.

**Ölçüm:**

| | doğru CA | yanlış CA | varsayılan |
|---|---|---|---|
| Apple `curl` | exit 0 | **exit 0** ❌ | exit 0 |
| Python `ssl` (OpenSSL) | ✅ | ❌ reddetti | ❌ reddetti |

**Çözüm:** Motor `curl` alt süreci yerine **Python `urllib` + `ssl.create_default_context(cafile=…)`**
kullanıyor. Doğrulamanın gerçekten yapıldığı ölçülebiliyor. Bundle `sertifika/kur.sh`
ile üretilir.

⚠️ Kök sertifika **DigiCert Global Root G2**'dir — "DigiCert Global Root CA" **değil**.
Yanlış kökle `openssl verify` sessizce başarısız olur.
⚠️ Ara sertifika **02.11.2027**'ye kadar geçerli; o tarihten önce `kur.sh` yeniden koşulmalı.

---

## 19.09.2026 — Dipnotlar madde gövdesine karışıp sahte "değişti" üretiyor

**Belirti:** Bir maddeye eklenen dipnot, **başka** bir maddenin gövde hash'ini
değiştirebiliyordu.

**Kök neden:** `pdftotext -layout` sayfa altındaki dipnotları metin akışına serpiştirir.
Bir sayfa kırılması maddenin ortasına denk gelirse, o maddenin çıkarılan gövdesine
komşu maddenin dipnotu girer. **Ölçüm: 4857'de 132 maddenin 22'sinde bu oluyor.**

**Çözüm (Ö-10):** `analiz.dipnot_ayir()` dipnot bloklarını (`^\d{1,3}$` satırı +
ardından `GG/AA/YYYY tarihli ve …`) gövdeden ayırır; hash **temiz gövdeden** alınır.
Dipnotlar atılmaz, `dipnot_blok` alanında saklanır — değişiklik tarihçesi oradadır.
Durum tespiti (yürütme durdurma/iptal) **ham gövdeden** yapılır, çünkü şerh dipnotta
da geçebilir.

---

## 19.09.2026 — Yarıda kesilen koşu tüm ilerlemeyi kaybediyordu

**Belirti:** İlk tam indirme 42/45'te kesildi. Sonuç: `durum.json` yok, `metin/` boş,
`pdf/` içinde 42 artık `*.yeni.pdf`.

**Kök neden:** Tüm yazma işi döngüden **sonra** yapılıyordu.

**Çözüm:** İlk indirme sonuçları döngü **içinde** hemen yazılır (karşılaştırılacak eski
nüsha olmadığı için devre kesiciyi ilgilendirmez); yalnız **değişenler** devre kesici
geçtikten sonra yazılır. Ayrıca her koşu başında `motor.artiklari_temizle()` artık
dosyaları siler.

**İkinci sızıntı:** "değişmemiş" sonucunda da geçici dosya siliniyordu sanılıyordu —
silinmiyordu. Her denetimde 24 artık dosya birikiyordu. `motor.kalem()` artık
`sonuc == "ayni"` durumunda da temizliyor.

---

## 19.09.2026 — `y-yapi-denetimi` numarası yanlıştı (12452 → 11951)

**Belirti:** Yapı Denetimi Uygulama Yönetmeliği hiçbir adresten gelmiyordu.
`5levent/araclar/mevzuat-kayit.json` bu belgeyi mevzuat.gov.tr yerine
`webdosya.csb.gov.tr`'den çekiyordu.

**Kök neden:** Kayıttaki mevzuat numarası (12452) yanlıştı. Resmî arama API'si
(`AranacakYer: "Baslik"`, `"Yapı Denetimi Uygulama"`) **no=11951, tertip=5** döndürdü;
o numarayla `GeneratePdf` 112.005 karakter metin verdi.

**Ders:** `OKU.md`'deki kural doğruymuş — *"Yeni kayıt eklerken `ara` komutuyla
DOĞRULA, tahmin etme."* Ayrıca bu yüzden `anahtar` (içerik doğrulama) alanı devreye
alındı: adres kalıbı birden çok aday denediği için yanlış numara **başka bir mevzuatın**
PDF'ini getirebilir ve sistem onu sessizce izlemeye başlar.

**Yan bulgu:** `y-yangin` "PDF'i yok, iframe şart" diye kayıtlıydı. `GeneratePdf`
gerçekten HTTP 600 veriyor — ama statik yol `MevzuatMetin/21.5.200712937.pdf`
**çalışıyor** (105 sayfa, 178 madde). Çok adaylı adres tasarımı bunu kendiliğinden buldu.
