---
name: degisiklikler
description: mevzuat projesinin DEĞİŞİKLİK RAPORU — izlenen kanun/yönetmeliklerdeki madde değişikliklerini (mevzuat.gov.tr) ve ilgili Resmî Gazete kayıtlarını sondan geriye, NUMARALI olarak iki grupta listeler — son rapordan sonra gelenlerin HEPSİ + öncesinden en yeni 10 tanesi. Numara verilince ("5'i detaylandır") o değişikliğin eski/yeni lafzını, kelime farkını, atıf yapan belgeleri ve RG metnini çıkarır; ne değiştiğini ayrıntılı raporlar ve doğurduğu sonucu yorumlar. Kullanıcı "/degisiklikler", "değişiklikleri raporla", "değişiklik raporu", "mevzuatta ne değişti", "son rapordan beri ne oldu", "yeni değişiklik var mı", "değişiklik listesi", "5'i detaylandır", "3 numarayı aç", "7'yi yorumla", "bu değişiklik ne anlama geliyor" dediğinde MUTLAKA bu skill kullanılmalı. Yalnız ~/Projects/mevzuat içindir. Projenin sistem analizi için `raporla`, tek bir maddenin lafzı için doğrudan `mevzuat.py madde` kullanılır.
---

# Değişiklik raporu (/degisiklikler)

İki mod vardır. Kullanıcının cümlesinden seç, sorma:

| Kullanıcı | Mod |
|---|---|
| "/degisiklikler", "ne değişti", "rapor ver" | **LİSTE** |
| "5'i detaylandır", "3 numara", "5 ve 8'i aç" | **DETAY** (her numara için ayrı) |
| "bir bakayım ama işaretleme", "sadece göster" | **LİSTE `--kuru`** |
| "listeyi tekrar göster", "tabloyu yeniden ver" | **LİSTE `--son`** — son listeyi AYNI numaralarla basar, hiçbir şey yazmaz |

Motor `degisiklik.py`'dir; iki kaynağı tek zaman çizelgesinde birleştirir:
`gunluk.json` (madde olayları) + `kayit/rg-gorulen.json` (Resmî Gazete kayıtları).
Numaralar ve "son rapor" işareti `kayit/rapor-durum.json`'da durur — **elle düzenlenmez.**

---

## LİSTE

```bash
cd ~/Projects/mevzuat && python3 mevzuat.py degisiklikler
```

Bu komut "son rapor" işaretini **ilerletir**: bir sonraki raporda A grubu yalnız bundan
sonra gelenleri içerir. Kullanıcı yalnız göz atmak istiyorsa `--kuru` ekle (numaralar yine
kaydedilir, detay yine çalışır; yalnız işaret ilerlemez).

Çıktıyı kullanıcıya şöyle sun:

1. **Tazelik uyarısı varsa (⚠) EN BAŞA** yaz: "günlük iş X'ten beri koşmamış, liste eksik
   olabilir." A grubu boşsa bu özellikle önemlidir — *"yeni değişiklik yok"* ile *"kimse
   bakmadı"* aynı şey değildir.
2. Tek satır başlık: rapor zamanı · önceki rapor · son denetim.
3. Dört numaralı grup — numaralar A'dan D'ye kesintisizdir:

   | Grup | İçerik |
   |---|---|
   | **A** | Son rapordan sonra — madde değişiklikleri + RG kayıtları (hepsi) |
   | **B** | Daha önce — aynıları, en yeni 10 |
   | **C** | Anayasa Mahkemesi kararları — son rapordan sonra (hepsi) |
   | **D** | Anayasa Mahkemesi kararları — daha önce, en yeni 10 |

   - Numaraları **script'in verdiği gibi** yaz. Yeniden numaralama, birleştirme, kalem
     atlama YOK — kullanıcı bu numarayla detay isteyecek.
   - A/B kalemi başına tek satır: `**5.** 🔴 25.09.2026 · Ayakta Teşhis Yön. — m.12 metni değişti ★`
     (📰 = Resmî Gazete kaydı, ★ = kaynak.json'da kritik madde). Uzun belge adları
     tanınır kalacak şekilde kısaltılabilir.
   - **C/D (AYM) TABLO olarak** (kullanıcı bu biçimi onayladı, 26.09.2026):

     | No | | Tür | Konu | Sonuç |
     |---|---|---|---|---|
     | **9** | 🩺 | bireysel | İkiz doğumda tıbbi ihmal iddiası… | ❗ İHLAL VAR |
     | **13** | | norm | CMK m.283 … | ✖️ RET |

     - İkinci sütun **🩺** = konu sağlıkla ilgili. Script `🩺 SAĞLIK` yazdıysa koy; konu
       açıkça sağlık hukukuysa (hekim, hastane, tıbbi müdahale, ilaç, SGK sağlık) ama
       script kaçırdıysa sen de koy. 🩺'lı satırın numarasını **kalın** yaz.
     - Sonuç, script'in işaretiyle başlar: **❗** ihlal bulundu / kural iptal edildi ·
       **✖️** ret / ihlal yok / kabul edilemez · **➖** karar verilmesine yer yok / düşme ·
       **❔** okunamadı. Tablonun altına bu açıklamayı tek satır yaz.
     - Script `konu` ve `sonuç` alanlarını karar metninden (çoğu OCR) çıkarır; sen **konuyu
       tek cümleye indir** ve OCR bozukluklarını anlam değiştirmeden düzelt. Norm denetiminde
       konu = hangi kanunun hangi maddesi; bireysel başvuruda = hangi olay, hangi hak.
       `konu okunamadı` / `hüküm okunamadı` varsa öyle yaz, **tahmin etme**.
       Kişi adları (başvurucu, üyeler) yazılmaz.
   - AYM'de öne çıkar: önce **🩺** satırlar, sonra **❗ İPTAL** sonuçlu norm kararları (bir
     kanun maddesi değişiyor), sonra kullanıcının öteki alanlarına değenler (iş hukuku,
     kat mülkiyeti, vergi…). Kaçının ✖️ olduğunu tek cümleyle söyle.
4. Listenin altında **2–4 cümle "öne çıkanlar"** — yalnız A ve C gruplarından, yalnız çıktıdaki
   olgularla: kaç kritik var, hangi belge/madde, RG'de yayımlanıp konsolide metne henüz
   işlenmemiş bir değişiklik var mı. **Hukuki yorum burada yapılmaz** — o, detayın işi.
5. Son satır: *"Detay için numara yazın (örn. '5'i detaylandır')."*

AYM kararlarının metni ilk görüldüğünde indirilip OCR'lanır — liste komutu yeni AYM kararı
varsa **karar başına ~5–30 sn** sürer (ilerleme stderr'e basılır); sonrası önbellekten gelir.

---

## DETAY

```bash
cd ~/Projects/mevzuat && python3 mevzuat.py degisiklik <no>          # --tam: kesilmemiş çıktı
```

- Numara **en son üretilen listeye** göredir; çıktının ilk satırı hangi listeye baktığını
  söyler. Kullanıcı eski bir konuşmadaki numarayı soruyorsa ve liste o zamandan beri
  yenilendiyse bunu belirt.
- RG belgesi ilk açılışta indirilir; PDF'in metin katmanı yoksa (AYM ve EPDK kararları)
  OCR yapılır — **~5–30 sn**. Sonraki açılışlar `kayit/rg-belge/` önbelleğinden gelir.

### Paketin içinde ne var

| Kalem türü | Script'in verdikleri |
|---|---|
| ⚖️ **Madde olayı** | olay kaydı · kaynak.json'daki *neden izleniyor* gerekçesi · aynı değişiklikteki diğer olaylar · **ESKİ METİN** ve **YENİ METİN** (maddenin tamamı) · **KELİME FARKI** · atıf yapan belgeler (**GÜÇLÜ**: belgenin adını da anan dosyalar / **ZAYIF**: yalnız çıplak "m.12") · ilgili RG kayıtları |
| 📰 **RG kaydı** | fihrist künyesi, neden yakalandığı · **RG METNİ** (AYM'de giriş + HÜKÜM) · izlenen bir belgeyse *konsolide metne işlendi mi* |

Eski nüsha üç yoldan aranır (arşiv kopyası → farkı ters uygulama → git) ve her biri imzayla
doğrulanır. Kurulamazsa script bunu ve nedenini söyler; o zaman "YAKLAŞIK" etiketli fark
blokları gelir.

### Yanıtın biçimi

```
### #5 — <kısa başlık>

**Özet** — 2-3 cümle: ne oldu, ne zaman, hangi kaynaktan tespit edildi.

**Ne değişti**
<madde olayı> Değişen fıkra/ibarenin ESKİ ve YENİ lafzı, tırnak içinde, madde/fıkra
  numarasıyla. Kelime farkını düz Türkçeyle anlat. Yalnız şerh kalktıysa (YD kalktı):
  hangi ibare/fıkra yeniden yürürlükte, üzerindeki Danıştay künyesi (daire, tarih, E. no) neydi.
  Aynı değişiklikteki diğer olayları bir cümleyle an.
<RG kaydı> Yayımlanan metin neyi ekliyor/değiştiriyor/kaldırıyor, yürürlük tarihi.
  AYM: itiraz konusu kural + HÜKÜM (iptal mi, ret mi, iptal hükmünün yürürlüğü ertelendi mi).
  Bireysel başvuru: konu + hangi hakta ihlal bulundu. EPDK: hangi şirket/tarife/eşik.

**Sonuç ve yorum**
- Hukuki sonuç: bugün ne yürürlükte, ne değil, ne zamandan beri, kimi bağlar.
- Bana etkisi: "Neden izleniyor" gerekçesini mercek olarak kullan (muayenehane, işveren
  statüsü, site yönetimi, fatura…). GÜÇLÜ etki dosyalarını adıyla an ve içlerinde neyin
  bayatlamış olabileceğini söyle — gerekirse ilgili satırları oku. ZAYIF listeden
  iddia kurma.
- Yapılacaklar: somut ve kısa (hangi belge güncellenmeli, neye tekrar bakılmalı).
  Dosya değiştirmeyi ÖNER, kendiliğinden yapma.
- Bilinmeyen: metnin söylemediği şeyi tahmin etme; neyin bilinmediğini ve nasıl
  öğrenileceğini yaz.

**Güvenilirlik** — tek satır: eski nüsha nereden (imza ✓), OCR/yaklaşık fark uyarısı.
```

Birden çok numara istendiyse her biri kendi başlığıyla; çok sayıdaysa önce kritik olanlar.
Kullanıcı kalemlerin ilişkili olduğunu söylerse (ya da aynı karar/aynı belge zincirindeyse)
önce ortak çerçeveyi tek tabloda ver, sonra her kalemi kısa tut.

**Detay yanıtı her zaman aşağıdaki BAYATLAYAN BELGELER adımıyla biter.**

---

## BAYATLAYAN BELGELER — onaylı, tarihli güncelleme

Kullanıcı kararı (25.09.2026): değişiklik raporunun sonunda bayatlayan belge varsa
**onay alınarak**, belgeye *"şu tarihte bu bilgi şöyle değişti"* notu düşülür.

1. **Tespit.** Paketteki **GÜÇLÜ** etki dosyalarında değişen hükümle ilgili satırları oku
   (`grep -n` + çevresi). *Bayat* = değişiklikten önceki durumu bugünün gerçeği gibi anlatan
   ifade: "durdurulmuştur", "askıya alınmıştır", eski lafız alıntısı, eski oran/süre/tarih,
   "hâlâ yok". Koşullu ifadeler ("şerh kalkarsa…") bayat değildir.
   - Script'in `🔄 <olay> işlendi` diye işaretlediği dosyalar **atlanır** (zaten yapılmış).
   - ZAYIF listeden bir dosya ancak satırı okununca aynı belgeye atıf yaptığı görülürse girer.
   - Aynı zincirde görülen ama **olay kaydı olmayan** bayatlık (aynı fark dosyasındaki başka
     fıkra, RG'de gelen değişiklik yönetmeliği) ayrı başlıkta ve kaynağıyla önerilir.
2. **Öneri.** Dosya başına: `dosya:satır` · bugün ne diyor (kısa) · düşülecek not. Lafız
   gerekiyorsa `mevzuat.py madde` ile okunmuş olmalı.
3. **Onay.** AskUserQuestion (dosya bazında, çoklu seçim) ya da açık soru. **Onay gelmeden
   hiçbir dosyaya yazılmaz.** Onay dosya başınadır; bir dosyaya verilen onay diğerine geçmez.
4. **Uygulama — eski metin SİLİNMEZ, yeniden yazılmaz; yanına tarihli not düşülür:**
   - Paragraf / liste / alıntı → ifadenin hemen altına:
     ```
     > 🔄 **GG.AA.YYYY'de değişti:** <yeni durum, 1–2 cümle>. Kaynak: mevzuat.gov.tr konsolide metni · `mevzuat` olay O-…
     ```
   - Tablo satırı → ilk hücredeki hüküm üstü çizilir (`~~m.12/1~~`), son hücrenin sonuna
     ` — 🔄 **GG.AA.YYYY:** <yeni durum> (O-…)`.
   - **Tarih** = değişikliğin olduğu gün: tek günde tespit edildiyse o gün; bir aralıkta
     olduysa *"07.09–19.09.2026 arasında değişti (19.09.2026'da tespit)"*; RG'den gelen
     değişiklikte RG yayım günü. Değişikliğin **hukuki** tarihi (karar günü) bilinmiyorsa
     uydurulmaz — tespit tarihi yazılır.
   - Not **olay kimliğini taşır** (`O-…` ya da `RG-…`): bir sonraki raporda dosya
     "🔄 işlendi" görünür ve aynı öneri tekrar gelmez.
   - **PDF üreten script'ler (`gen_*.py`)** ve **paylaşılmış/teslim edilmiş belgeler** ayrı
     sorulur: metin dizesi değişecekse satır üstüne `# 🔄 GG.AA.YYYY: … (O-…)` yorumu;
     PDF **kendiliğinden yeniden basılmaz**. Paylaşılmış/imzalı belgenin düzeltme yolu
     yeni basım değil düzeltme notudur (zeyilname).
   - Hedef projenin `CLAUDE.md` kuralları (dil, belge düzeni) geçerlidir.
5. **Doğrulama.** Her dosyada `grep -c "<olay kimliği>"` ≥ 1 ve `git -C <proje> diff --stat`;
   dosya başına bir satır rapor. **Commit atılmaz** — kullanıcı isterse ayrı adım.

---

## Kesin kurallar

1. **Lafız yalnız iki yerden:** script çıktısı ya da `python3 mevzuat.py madde <slug> <no>`.
   Yorum başka bir maddeye dayanıyorsa (kapsam maddesi, dayanak kanun maddesi) **önce o
   maddeyi `madde` ile oku, sonra an.** Hafızadan madde, oran, süre, nisap yazılmaz.
2. **Sayı ve tarih** yalnız okunan metinde harfiyen geçiyorsa yazılır.
3. **OCR metni** (çıktıda "OCR (pdf-md.sh)" yazar) sayı ve özel adda hata yapar
   (ölçülen örnek: "Şanlıurfa" → "Şanhurfa"). Kullandığın her sayıyı başlık/fihristle
   karşılaştır ya da "OCR metninden" diye etiketle.
4. **RG metni konsolide metin değildir.** İzlenen bir belgenin değişikliği RG'de yayımlanıp
   mevzuat.gov.tr'ye henüz işlenmediyse bunu açıkça yaz: *"RG'de yayımlanan değiştirici
   metin; konsolide metne henüz işlenmedi."* Konsolide madde lafzı için tek kaynak
   mevzuat.gov.tr'dir (global kural).
5. **Yürütmeyi durdurma şerhinin kalkması** sebebini metin söylemez (karar kaldırılmış,
   dava reddedilmiş, idare yeni düzenleme yapmış olabilir). Sebep uydurulmaz; öğrenme yolu
   `python3 danistay.py "<belge adı>" <E. no>` — elle araştırma aracıdır, yayını gecikmelidir.
6. Bu skill **yalnız okur.** `gunluk.json`, `durum.json`, `kaynak.json` elle düzenlenmez;
   `kayit/rapor-durum.json`'a script dışında dokunulmaz.
7. Tazelik uyarısında `python3 mevzuat.py denetle` (~3,5 dk, durum/günlük yazar) önerilebilir;
   **kullanıcıya sormadan koşulmaz.** `gunluk_is.py` Bark bildirimi de gönderir — elle koşma.

## Bilinmesi gerekenler

- **Otomatik yayın ayrıdır:** her sabah 09:00 günlük özet ve gün içinde acil bildirim
  `https://mevzuat-ozet.vercel.app` sayfalarıyla gider (`yayin.py`, `acil_is.py`). O sayfaların
  "yayımlandı" kaydı (`kayit/yayin-durum.json`) bu skill'in "son rapor" işaretinden
  (`kayit/rapor-durum.json`) **bağımsızdır** — biri ötekini ilerletmez. Kullanıcı "bildirimde
  gelen şu değişiklik" derse o sayfadaki başlıkla listede eşleştir.

- **"Yeni" kimliğe göre belirlenir, zamana göre değil.** RG taraması 3 günlük pencereyle
  koşar; iki gün önceki bir yayım bugün ilk kez görülebilir ve yine A grubuna düşer.
- **AYM kararları C/D grubunda, tek tek** listelenir. Bireysel başvuru (⚪ bilgi) normu
  değiştirmez — hak ihlali tespitidir; norm denetimi (`E: …, K: …`, 🔴) iptal getirebilir.
  Sonuç, hüküm fıkrasındaki **BÜYÜK HARFLİ** kelimelerden okunur ("İHLAL EDİLDİĞİNE",
  "REDDİNE"); küçük harfli "ihlal edildiğine ilişkin iddia" sonuç değildir.
- `www.resmigazete.gov.tr` mevzuat.gov.tr ile aynı eksik sertifika zincirini gönderir;
  script projenin `sertifika/mevzuat-ca.pem` bundle'ını kullanır. **`-k` kullanılmaz.**
  Bundle yoksa: `bash sertifika/kur.sh`.

## Hata durumları

| Çıktı | Ne yap |
|---|---|
| "Henüz rapor alınmamış" | Önce LİSTE modunu koş |
| "#N son listede yok … 1–M arası" | Kullanıcıya aralığı söyle |
| "⚠ Belge okunamadı" / "Fihrist alınamadı" | URL'yi ve hatayı aynen aktar; içeriği tahmin etme |
| "eski nüsha kurulamadı" | YAKLAŞIK blokları kullan, yanıtta "eski metnin tamamı yok" de |
