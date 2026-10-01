# TODO — mevzuat

> Kurulum 19.09.2026'da tamamlandı. Tarama raporu: [`mevzuat_tara.md`](mevzuat_tara.md),
> öneri defteri: `mevzuat_tara.json`.

## Açık

### Yönetmelik sonundaki künye tablosu son maddeye karışıyor → sahte "madde değişti"
**Ne:** 26.09.2026'da Uzaktan Çalışma Yönetmeliği değişince **m.16 metni değişti** olayı da üretildi;
oysa m.16 değişmedi — yönetmeliğin sonundaki "Yönetmeliğin Yayımlandığı Resmî Gazete'nin Tarihi
Sayısı / Değişiklik Yapan Yönetmelikler" tablosuna yeni satır eklendi ve `analiz.KUYRUK` bu tabloyu
kesmediği için son maddenin gövdesine sayıldı. Her yönetmelik değişikliğinde son madde için bir
sahte olay (ve acil bildirim) üretir.
**Nerede:** `analiz.py` `KUYRUK` deseni — "Yönetmeliğin Yayımlandığı Resmî Gazete" başlığı eklenmeli.
**Dikkat:** Desen değişince bütün yönetmeliklerin son madde hash'i değişir; imza değişmediği için
olay üretmez ama bir sonraki gerçek değişiklikte o belgede son madde için bir kez sahte olay
çıkabilir → değişiklikten sonra `denetle --kuru` ile ölç.

### Mac kapalıyken bildirim yok
**Ne:** Günlük ve acil işler bu Mac'te (launchd). Mac kapalı/uykudaysa uyanınca bir kez koşar.
**Seçenek:** VPS'e taşımak — ama AYM/EPDK PDF'leri macOS Vision OCR'ı gerektiriyor; TLS bundle ve
pdftotext de taşınmalı. Karar kullanıcıda.

### `yayin/` arşivi yalnız bu Mac'te
**Ne:** Her deploy klasörün tamamını yükler; klasör kaybolursa eski günlerin sayfaları da yayından
kalkar. `kayit/yayin-durum.json` ve `gunluk.json`'dan yeniden üretilebilir ama aracı yok.

### `fatura` grubu eklendi (20.09.2026) — 2027 eşik kararı beklenecek
**Ne:** 6 yeni kayıt (`grup: fatura`): SKTT Tebliği, Elektrik Piyasası Tüketici Hizmetleri
Yönetmeliği, 6446, Tarifeler Yönetmeliği, 2464, 2560. `rg.py`'ye EPDK Kurul Kararı süzgeci
eklendi — o kararlar mevzuat.gov.tr'de yayımlanmıyor (bkz. `COZUMLER.md` 20.09.2026).
**Neden bekliyor:** EPDK mesken son kaynak eşiğini her yıl yeniden belirliyor ve düşürüyor
(2025: 5.000 → 2026: 4.000 kWh/yıl). 2027 kararı **Ekim–Aralık 2026**'da çıkacak; süzgeç
o pencerede "AÇ" uyarısı basacak. Karar çıkınca `~/Projects/fatura/TODO.md` ve
`hesap/analiz.py`'deki limit güncellenmeli.

### Ö-12 · Metinleri git geçmişine tam oturt
**Ne:** `metin/*.txt` sürüm denetiminde; her denetim bir commit olsun ve
`git diff --word-diff --color-moved=zebra` taşınan madde bloklarını göstersin.
**Neden bekliyor:** Otomatik commit akışı henüz kurulmadı; `gunluk_is.py` şu an
commit atmıyor. Kullanıcı kararı gerekiyor: her denetim commit mi, yalnız değişiklikte mi?

### Bedesten (UYAP) API'si yedek kaynak
**Ne:** `bedesten.adalet.gov.tr/mevzuat` madde-bazlı erişim ve gerekçe sunuyor.
**Engel:** Bu ağdan **erişilemedi** (503/zaman aşımı, muhtemel WAF). `acik-mevzuat`
projesinin GitHub Actions senkronu aynı gün başarıyla koştuğu için API'nin kendisi
çalışıyor — sorun bizim çıkışımızda.
**İlk adım:** Farklı bir ağdan (VPS?) denenmeli.

### Yürürlük tarihi gelecekte olan hükümler
**Ne:** `y-ozel-hastaneler` m.53 "16 ncı maddesinin altıncı fıkrası 1/1/2026 tarihinde
yürürlüğe girer" diyor. Bu tarihler ayrıştırılıp takvime bağlanırsa sistem *olacak*
değişikliği de hatırlatır.

### Kuyruk tablosunu veri olarak oku
**Ne:** Kanunların sonundaki "EK VE DEĞİŞİKLİK GETİREN MEVZUATIN YÜRÜRLÜĞE GİRİŞ
TARİHLERİNİ GÖSTERİR TABLO" hangi kanunun hangi maddeleri ne zaman değiştirdiğini
**resmî olarak** listeliyor. Şu an ayrıştırıcı bu bölümü yalnız kesip atıyor.
Ayrıştırılırsa kendi diff'imizle çapraz doğrulanabilir.

## Bakım takvimi

| Ne zaman | Ne |
|---|---|
| **02.11.2027'den önce** | `bash sertifika/kur.sh` — ara sertifika o tarihte doluyor |
| `pdftotext` yükseltince | İlk `denetle` koşusunda devre kesici tetiklenebilir; `--devre-kesiciyi-atla` ile yeniden temel al |
| Yeni mevzuat eklerken | `python3 mevzuat.py ara` ile numarayı **doğrula**, `anahtar` alanını doldur |

## Tamamlandı (19.09.2026)

Ö-1 Resmî Gazete ikinci sinyali · Ö-2 etki analizi · Ö-3 kelime düzeyinde fark ·
Ö-4 belirsizlik kategorisi · Ö-5 tam metin arama · Ö-6 alt mevzuat tetiklemesi ·
Ö-7 Danıştay taraması (elle araç olarak) · **Ö-11 merkezîleştirme** · Ö-8 hibrit tespit · Ö-9 devre kesici +
sürüm damgası · Ö-10 normalizasyon + dipnot ayırma · Ö-13 TLS bundle · Ö-14 private depo
