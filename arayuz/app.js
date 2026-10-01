'use strict';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const api = (y, o) => fetch(y, o).then(r => r.json());
const kac = s => String(s ?? '').replace(/[&<>"']/g, m =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));

const DURUM_SINIF = { yururlukte: '', mulga: 'mulga', iptal: 'iptal',
                      yurutme_durduruldu: 'yurutme_durduruldu' };
const SIDDET_AD = { kritik: 'kritik', onemli: 'önemli', bilgi: 'bilgi' };

let LISTE = [], OZET = {};

// ───────────────────────────────────────── sekmeler
$$('.sekme').forEach(b => b.onclick = () => {
  $$('.sekme').forEach(x => x.classList.toggle('etkin', x === b));
  $$('.sayfa').forEach(s => s.classList.toggle('etkin', s.id === 's-' + b.dataset.sekme));
  if (b.dataset.sekme === 'gunluk') gunlukCiz();
  if (b.dataset.sekme === 'sistem') sistemCiz();
});

// ───────────────────────────────────────── özet
async function ozetYukle() {
  OZET = await api('/api/ozet');
  const m = OZET.madde || {};
  $('#ozet-satir').innerHTML =
    `${OZET.indirilen}/${OZET.izlenen} belge · ${OZET.toplam_madde} madde` +
    (m.yurutme_durduruldu ? ` · <b style="color:var(--kritik)">${m.yurutme_durduruldu} yürütmesi durdurulmuş</b>` : '') +
    (m.iptal ? ` · ${m.iptal} AYM iptali` : '') +
    (OZET.son_dogrulama ? ` · son denetim ${kac(OZET.son_dogrulama)}` : '');
  $('#r-mevzuat').textContent = OZET.izlenen;
  $('#r-gunluk').textContent = OZET.okunmamis || '';
}

// ───────────────────────────────────────── mevzuat listesi
async function listeYukle() {
  const d = await api('/api/liste');
  LISTE = d.mevzuat;
  mevzuatCiz();
}
function mevzuatCiz() {
  const f = $('#mevzuat-filtre').value.trim().toLowerCase();
  const s = $('#mevzuat-sinif').value, g = $('#mevzuat-grup').value;
  const yo = $('#yalniz-olayli').checked, ya = $('#yalniz-acil').checked;
  const sz = LISTE.filter(m =>
    (!f || (m.ad + ' ' + m.slug + ' ' + m.no).toLowerCase().includes(f)) &&
    (!s || m.sinif === s) && (!g || (m.grup || []).includes(g)) &&
    (!yo || m.olay_sayisi > 0) && (!ya || m.acil));
  $('#acil-sayi').textContent = `🚨 acil bildirim: ${LISTE.filter(m => m.acil).length} belge`;
  $('#mevzuat-liste').innerHTML = sz.length ? sz.map(kartHtml).join('')
    : '<div class="bos">Eşleşen mevzuat yok.</div>';
  $$('#mevzuat-liste .kart').forEach(k =>
    k.onclick = () => belgeAc(k.dataset.slug));
  // Acil seçimi: kartın kendisi belgeyi açar, düğme yalnız seçimi değiştirir.
  $$('#mevzuat-liste [data-acil]').forEach(b => b.onclick = async ev => {
    ev.stopPropagation();
    const m = LISTE.find(x => x.slug === b.dataset.acil);
    b.disabled = true;
    const d = await api('/api/acil', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slug: m.slug, acil: !m.acil }) });
    if (d.tamam) { LISTE.forEach(x => x.acil = d.sluglar.includes(x.slug)); }
    else { alert('Acil seçimi kaydedilemedi: ' + (d.hata || '?')); }
    mevzuatCiz();
  });
}
function kartHtml(m) {
  const o = m.madde_ozeti || {};
  const et = [`<span class="etiket ${m.sinif === 'cekirdek' ? 'cekirdek' : ''}">${m.sinif}</span>`];
  if (o.yurutme_durduruldu) et.push(`<span class="etiket kritik">${o.yurutme_durduruldu} yürütme durdurma</span>`);
  if (o.iptal) et.push(`<span class="etiket onemli">${o.iptal} AYM iptali</span>`);
  if (o.mulga) et.push(`<span class="etiket">${o.mulga} mülga</span>`);
  if (m.mukerrer && m.mukerrer.length) et.push(`<span class="etiket onemli" title="Ayrıştırıcı bu maddeleri kesin eşleştiremedi">⚠ ${m.mukerrer.length} belirsiz</span>`);
  (m.grup || []).forEach(x => et.push(`<span class="etiket bilgi">${kac(x)}</span>`));
  return `<div class="kart${m.acil ? ' acil-kart' : ''}" data-slug="${kac(m.slug)}">
    <button class="acil-dugme${m.acil ? ' acik' : ''}" data-acil="${kac(m.slug)}"
      title="${m.acil ? 'Acil bildirim AÇIK — değişiklik gün içinde hemen bildirilir. Kapatmak için tıkla.'
                      : 'Acil bildirim kapalı — değişiklik ertesi sabahın günlük özetinde gelir. Açmak için tıkla.'}">
      🚨 ${m.acil ? 'acil' : 'acil değil'}</button>
    <h3>${kac(m.ad)}</h3>
    <div class="slug">${kac(m.slug)} · ${kac(m.no)} · ${m.madde ?? '—'} madde</div>
    <div class="etiketler">${et.join('')}</div>
    <div class="zaman">
      <span>son denetim <b>${kac(m.son_dogrulama || 'hiç')}</b></span>
      <span>${m.olay_sayisi ? `<span class="tikla">${m.olay_sayisi} olay</span>` : 'değişiklik yok'}
        ${m.okunmamis ? '<span class="nokta"></span>' : ''}</span>
    </div></div>`;
}

// ───────────────────────────────────────── belge katı
async function belgeAc(slug) {
  const d = await api('/api/belge/' + encodeURIComponent(slug));
  if (d.hata) return;
  const k = d.kaynak, du = d.durum;
  const say = {};
  d.maddeler.forEach(m => say[m.durum] = (say[m.durum] || 0) + 1);
  const ozel = d.maddeler.filter(m => m.durum !== 'yururlukte');

  $('#kat-icerik').innerHTML = `
    <h2>${kac(k.ad)}</h2>
    <div class="alt">${kac(k.slug)} · ${kac(k.tur)} ${kac(k.no)} · tertip ${kac(k.tertip)}
      · sınıf <b>${kac(k.sinif)}</b> · ${(k.grup || []).join(', ')}</div>

    <div class="bolum"><h4>Neden izleniyor</h4>
      <div style="font-size:13.5px;line-height:1.65">${kac(k.neden || '—')}</div></div>

    <div class="bolum"><h4>Durum</h4>
      <table>
        <tr><th>son doğrulama</th><td>${kac(du.son_dogrulama || '—')}</td></tr>
        <tr><th>son değişiklik</th><td>${kac(du.son_degisiklik || '—')}</td></tr>
        <tr><th>imza</th><td><code>${kac(du.imza || '—')}</code>
          <span class="alt">(${kac(du.imza_turu || '—')} hash'i)</span></td></tr>
        <tr><th>sayfa / madde</th><td>${du.sayfa ?? '—'} sayfa · ${du.madde ?? '—'} madde</td></tr>
        <tr><th>araç sürümü</th><td>pdftotext ${kac(du.arac_surumu || '—')}</td></tr>
        <tr><th>kaynak</th><td><a href="${kac(du.sayfa_url || '#')}" target="_blank" rel="noopener">mevzuat.gov.tr</a>
          · <a href="${kac(du.url || '#')}" target="_blank" rel="noopener">PDF</a></td></tr>
      </table></div>

    ${ozel.length ? `<div class="bolum"><h4>Dikkat gerektiren maddeler (${ozel.length})</h4>
      ${ozel.map(m => `<div class="olay ${m.durum === 'yurutme_durduruldu' || m.durum === 'iptal' ? 'kritik' : 'bilgi'}">
        <div class="ust"><span class="ad">madde ${kac(m.no)}</span>
          <span class="etiket ${m.durum === 'yururlukte' ? 'iyi' : 'kritik'}">${kac(m.durum_adi)}</span></div>
        ${m.kunye ? `<div class="kunye">${kac(m.kunye)}</div>` : ''}
        <div class="araclar"><button class="dugme kucuk" data-madde="${kac(m.no)}" data-slug="${kac(k.slug)}">lafzını oku</button></div>
      </div>`).join('')}</div>` : ''}

    <div class="bolum"><h4>Madde envanteri — ${d.maddeler.length} madde
      ${Object.entries(say).map(([a, b]) => `· ${b} ${kac(a)}`).join(' ')}</h4>
      <div class="madde-izgara">${d.maddeler.map(m =>
        `<div class="madde ${DURUM_SINIF[m.durum]} ${m.kritik ? 'kritik-madde' : ''}"
          data-madde="${kac(m.no)}" data-slug="${kac(k.slug)}"
          title="${kac(m.durum_adi)}${m.kritik ? ' · KRİTİK madde' : ''}">${kac(m.no)}</div>`).join('')}</div>
      <div class="alt" style="margin-top:7px">Çerçeveli olanlar <b>kritik madde</b> — değişikliği bildirim üretir.</div></div>

    ${d.olaylar.length ? `<div class="bolum"><h4>Bu belgedeki olaylar (${d.olaylar.length})</h4>
      <div class="zaman-cizgisi">${d.olaylar.map(olayHtml).join('')}</div></div>` : ''}

    ${d.farklar.length ? `<div class="bolum"><h4>Kayıtlı farklar</h4>
      ${d.farklar.map(f => `<button class="dugme kucuk" data-fark="${kac(f)}" data-slug="${kac(k.slug)}"
        style="margin:0 6px 6px 0">${kac(f.replace(k.slug + '_', '').replace('_fark.diff', ''))}</button>`).join('')}</div>` : ''}
  `;
  $('#kat').classList.remove('gizli');
  bagla();
}

function bagla() {
  $$('[data-madde]').forEach(e => e.onclick = ev => {
    ev.stopPropagation(); maddeAc(e.dataset.slug, e.dataset.madde);
  });
  $$('[data-fark]').forEach(e => e.onclick = ev => {
    ev.stopPropagation(); farkAc(e.dataset.slug, e.dataset.fark);
  });
  $$('[data-okundu]').forEach(e => e.onclick = async ev => {
    ev.stopPropagation();
    await api('/api/olay/okundu', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: e.dataset.okundu, okundu: e.dataset.deger === '1' }) });
    await ozetYukle(); gunlukCiz();
  });
}

async function maddeAc(slug, no) {
  const d = await api(`/api/madde?slug=${encodeURIComponent(slug)}&no=${encodeURIComponent(no)}`);
  if (d.hata) { alert(d.hata); return; }
  $('#kat-icerik').innerHTML = `
    <h2>${kac(d.ad)} — madde ${kac(d.no)}</h2>
    <div class="alt">${kac(d.durum_adi)} · son doğrulama ${kac(d.son_dogrulama || '—')}</div>
    ${d.kunye ? `<div class="bilgi-kutu" style="margin-top:12px">${kac(d.kunye)}</div>` : ''}
    <div class="bolum"><pre>${kac(d.metin)}</pre></div>
    ${d.dipnot_blok && d.dipnot_blok.length ? `<div class="bolum"><h4>Dipnotlar (gövdeden ayrıldı)</h4>
      ${d.dipnot_blok.map(x => `<div class="alt" style="margin-bottom:6px">${kac(x)}</div>`).join('')}</div>` : ''}
    <div class="bolum"><a href="${kac(d.sayfa_url)}" target="_blank" rel="noopener">mevzuat.gov.tr'de aç</a>
      · <button class="dugme kucuk" id="geri-belge" data-slug="${kac(slug)}">◀ belgeye dön</button></div>`;
  $('#geri-belge').onclick = () => belgeAc(slug);
}

async function farkAc(slug, dosya) {
  const d = await api(`/api/fark?slug=${encodeURIComponent(slug)}&dosya=${encodeURIComponent(dosya)}`);
  if (d.hata) { alert(d.hata); return; }
  const kelime = (d.kelime || []).map(blok => `<div class="fark-blok fark">${
    blok.map(p => p.t === 'e' ? kac(p.m)
      : p.t === '+' ? `<span class="ek">${kac(p.m)}</span>`
      : `<span class="sil">${kac(p.m)}</span>`).join(' ')}</div>`).join('');
  $('#kat-icerik').innerHTML = `
    <h2>Fark — ${kac(slug)}</h2><div class="alt">${kac(dosya)}</div>
    <div class="bilgi-kutu" style="margin-top:12px">
      <b>Kelime düzeyinde karşılaştırma.</b>
      <span class="ek">yeşil = eklendi</span> · <span class="sil">kırmızı = silindi</span>.
      Satır düzeyindeki ham fark aşağıda.</div>
    <div class="bolum"><h4>Kelime farkı (${(d.kelime || []).length} blok)</h4>
      ${kelime || '<div class="bos">Blok çıkarılamadı.</div>'}</div>
    <div class="bolum"><h4>Ham satır farkı</h4><pre>${kac(d.diff)}</pre></div>
    <div class="bolum"><button class="dugme kucuk" id="geri-belge2">◀ belgeye dön</button></div>`;
  $('#geri-belge2').onclick = () => belgeAc(slug);
}

// ───────────────────────────────────────── günlük
function olayHtml(o) {
  return `<div class="olay ${kac(o.siddet || 'bilgi')}">
    <div class="ust">
      <span class="ad">${kac(o.ad || o.slug || '')}</span>
      <span class="alt">${kac(o.tarih || '')} ${o.okundu ? '' : '<span class="nokta"></span>'}</span>
    </div>
    <div class="etiketler">
      <span class="etiket ${kac(o.siddet)}">${kac(SIDDET_AD[o.siddet] || o.siddet || '')}</span>
      ${o.tur_adi ? `<span class="etiket">${kac(o.tur_adi)}</span>` : ''}
      ${o.madde ? `<span class="etiket cekirdek">m.${kac(o.madde)}</span>` : ''}
      ${o.kritik_madde ? '<span class="etiket kritik">kritik madde</span>' : ''}
    </div>
    <div class="ozet">${kac(o.ozet || '')}</div>
    ${o.kunye ? `<div class="kunye">${kac(o.kunye)}</div>` : ''}
    <div class="araclar">
      ${o.slug ? `<button class="dugme kucuk" data-slug="${kac(o.slug)}" data-belge="1">belgeyi aç</button>` : ''}
      ${o.fark_dosyasi ? `<button class="dugme kucuk" data-slug="${kac(o.slug)}"
         data-fark="${kac((o.fark_dosyasi || '').split('/').pop())}">farkı gör (${o.fark_satir || '?'} satır)</button>` : ''}
      ${o.id ? `<button class="dugme kucuk" data-okundu="${kac(o.id)}" data-deger="${o.okundu ? '0' : '1'}">
         ${o.okundu ? 'okunmadı işaretle' : 'okundu işaretle'}</button>` : ''}
    </div></div>`;
}
async function gunlukCiz() {
  const s = $('#gunluk-siddet').value;
  const ok = $('#gunluk-okunmamis').checked ? '&okunmamis=1' : '';
  const d = await api(`/api/gunluk?siddet=${s}${ok}`);
  $('#gunluk-sayi').textContent = `${d.olaylar.length} / ${d.toplam} olay`;
  $('#gunluk-liste').innerHTML = d.olaylar.length ? d.olaylar.map(olayHtml).join('')
    : '<div class="bos">Kayıtlı olay yok. İlk denetimden sonra buraya değişiklikler düşer.</div>';
  $$('[data-belge]').forEach(e => e.onclick = () => belgeAc(e.dataset.slug));
  bagla();
}

// ───────────────────────────────────────── Resmî Gazete
async function rgTara() {
  const g = $('#rg-gun').value || 7;
  $('#rg-durum').textContent = 'taranıyor…';
  $('#rg-liste').innerHTML = '<div class="bos">Resmî Gazete okunuyor…</div>';
  const d = await api('/api/rg?gun=' + g);
  $('#rg-durum').textContent = `${d.gun} gün okundu · ${d.bulgular.length} ilgili kayıt`
    + (d.hatalar.length ? ` · ${d.hatalar.length} gün okunamadı` : '');
  $('#rg-liste').innerHTML = d.bulgular.length ? d.bulgular.map(b => `
    <div class="olay ${b.siddet === 'kritik' ? 'kritik' : 'onemli'}">
      <div class="ust"><span class="ad">${kac(b.baslik)}</span>
        <span class="alt">${kac(b.tarih)} · RG ${kac(b.rg_sayi || '')}</span></div>
      <div class="etiketler">
        <span class="etiket">${kac(b.kategori || b.bolum)}</span>
        ${(b.sebep || []).map(s => `<span class="etiket ${s.startsWith('izlenen') ? 'cekirdek'
          : s.includes('YÜRÜTME') ? 'kritik' : 'bilgi'}">${kac(s)}</span>`).join('')}
      </div>
      ${b.url ? `<div class="araclar"><a class="dugme kucuk" href="${kac(b.url)}" target="_blank" rel="noopener">Resmî Gazete'de aç</a></div>` : ''}
    </div>`).join('')
    : '<div class="bos">Bu aralıkta ilgili kayıt yok.</div>';
}
$('#rg-tara').onclick = rgTara;

// ───────────────────────────────────────── ara
async function araYap() {
  const q = $('#ara-ifade').value.trim();
  if (q.length < 2) return;
  $('#ara-sonuc').innerHTML = '<div class="bos">aranıyor…</div>';
  const d = await api('/api/bul?q=' + encodeURIComponent(q));
  if (!d.sonuc || !d.sonuc.length) {
    $('#ara-sonuc').innerHTML = '<div class="bos">Sonuç yok.</div>'; return;
  }
  const vur = t => kac(t).replace(new RegExp('(' + q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi'),
    '<mark>$1</mark>');
  $('#ara-sonuc').innerHTML = d.sonuc.map(s => `
    <div class="olay bilgi">
      <div class="ust"><span class="ad">${kac(s.ad)}</span>
        <span class="alt">${s.toplam} geçiş</span></div>
      ${s.gecis.map(g => `<div style="margin-top:7px;font-size:13px">
        <button class="dugme kucuk" data-slug="${kac(s.slug)}" data-madde="${kac(g.madde)}"
          ${g.madde ? '' : 'disabled'}>${g.madde ? 'm.' + kac(g.madde) : 'satır ' + g.satir}</button>
        <span style="margin-left:7px">…${vur(g.baglam)}…</span></div>`).join('')}
    </div>`).join('');
  bagla();
}
$('#ara-btn').onclick = araYap;
$('#ara-ifade').addEventListener('keydown', e => { if (e.key === 'Enter') araYap(); });
// type=search kutusu Enter'da ve ✕ ile temizlemede 'search' olayı da yayar.
$('#ara-ifade').addEventListener('search', () => {
  if ($('#ara-ifade').value.trim()) araYap();
  else $('#ara-sonuc').innerHTML = '';
});

// ───────────────────────────────────────── sistem
async function sistemCiz() {
  const o = await api('/api/ozet');
  const m = o.madde || {};
  $('#sistem-icerik').innerHTML = `
    <div class="bolum"><h4>Sistem</h4><table>
      <tr><th>arayüz portu</th><td>${o.port} (yalnız 127.0.0.1)</td></tr>
      <tr><th>izlenen mevzuat</th><td>${o.izlenen} (${o.indirilen} indirilmiş)</td></tr>
      <tr><th>toplam madde</th><td>${o.toplam_madde}</td></tr>
      ${Object.entries(m).map(([a, b]) => `<tr><th>· ${kac(a)}</th><td>${b}</td></tr>`).join('')}
      <tr><th>olay</th><td>${o.olay} (${o.kritik} kritik · ${o.okunmamis} okunmamış)</td></tr>
      <tr><th>son denetim</th><td>${kac(o.son_dogrulama || '—')}</td></tr>
      <tr><th>pdftotext</th><td>${kac(o.poppler)}</td></tr>
      <tr><th>TLS</th><td>${kac(o.tls)}</td></tr>
    </table></div>
    <div class="bilgi-kutu" style="margin-top:18px">
      <b>Tespit hibrittir.</b> Kanun ve KHK statik dosyadır: bayt hash'i + koşullu GET
      (<code>If-None-Match</code>) kullanılır, değişmemiş belge hiç indirilmez.
      Yönetmelikler <code>GeneratePdf</code> ile anlık üretildiği için her indirmede
      farklı bayt verir; orada normalize <b>metin</b> hash'i esastır.
      Tek koşuda külliyatın %20'sinden fazlası değişmiş görünürse <b>devre kesici</b>
      devreye girer ve hiçbir şey güncellenmez — bu, pdftotext sürüm değişikliğinin
      sahte alarm üretmesini engeller.
    </div>`;
}

// ───────────────────────────────────────── denetim
async function denetimBaslat(tur) {
  $('#is-kutu').classList.remove('gizli');
  $('#is-ad').textContent = tur === 'rg' ? 'Resmî Gazete taraması' : 'Güncellik denetimi';
  $('#is-cikti').textContent = 'başlatılıyor…';
  await api('/api/denetle', { method: 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tur }) });
  const t = setInterval(async () => {
    const d = await api('/api/denetim');
    $('#is-cikti').textContent = d.cikti || 'çalışıyor…';
    $('#is-cikti').scrollTop = $('#is-cikti').scrollHeight;
    if (!d.kosuyor) {
      clearInterval(t);
      await ozetYukle(); await listeYukle(); gunlukCiz();
    }
  }, 1500);
}
$('#btn-denetle').onclick = () => denetimBaslat('denetle');
$('#btn-rg').onclick = () => { $$('.sekme').find(b => b.dataset.sekme === 'rg').click(); rgTara(); };
$('#is-kapat').onclick = () => $('#is-kutu').classList.add('gizli');
$('#kat-kapat').onclick = () => $('#kat').classList.add('gizli');
$('#kat').onclick = e => { if (e.target.id === 'kat') $('#kat').classList.add('gizli'); };
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') $('#kat').classList.add('gizli');
});
['#mevzuat-filtre', '#mevzuat-sinif', '#mevzuat-grup', '#yalniz-olayli', '#yalniz-acil']
  .forEach(s => $(s).addEventListener('input', mevzuatCiz));
['#gunluk-siddet', '#gunluk-okunmamis'].forEach(s => $(s).addEventListener('input', gunlukCiz));

ozetYukle(); listeYukle();
