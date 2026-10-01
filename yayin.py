#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
yayin.py — günlük özet ve acil bildirim SAYFALARI (public · mevzuat-ozet.vercel.app)

    python3 yayin.py gunluk [--gonderme] [--yayinlama]   günlük özet: üret → yayınla → doğrula → Bark
    python3 yayin.py onizle                              yalnız üret (yayin/), yayınlama ve bildirim yok
    python3 yayin.py dogrula <yol>                       yayındaki sayfayı HTTP ile doğrula

acil_is.py `acil(kalemler)` fonksiyonunu çağırır; gunluk_is.py `gunluk()`'ü.

KULLANICI KARARLARI (26.09.2026):
  · Rutin bildirim GÜNLÜK — değişiklik olmasa da gider: "değişiklik yok" demek
    "sistem çalıştı" demektir (eskiden olay yoksa sessiz geçiyordu).
  · Bildirime dokununca özet sayfası açılır: public, şifresiz, *.vercel.app.
  · Her değişiklikte hem NE DEĞİŞTİ (eski/yeni lafız, kelime farkı) hem de
    belgenin mevzuat.gov.tr LİNKİ.
  · Çekirdek belgelerde değişiklik → günlüğü beklemeden ACİL bildirim, aynı biçim.

GİZLİLİK — sayfa public olduğu için YAYIMLANMAYANLAR:
  · kaynak.json `neden` alanları (is-hukuku dava gerekçesi; depo bu yüzden private)
  · etki taraması (kendi belgelerimin yolları ve satırları)
  · olay kaydının `not` ve `kaynak` serbest metinleri (iç süreç notu)
  · iç dosya yolları (arsiv/…, metin/…)
  Yalnız resmî metin ve kamuya açık künye yayımlanır. test/test_yayin.py sınar.

YAYIN: yayin/ klasörü (git dışı) statik sitedir ve Vercel projesine CLI ile
yüklenir — depo Vercel'e BAĞLI DEĞİLDİR, yüklenen tek şey üretilmiş HTML'dir.
Yayın "200 OK" ile değil, sayfadaki yayın kimliğinin canlıda okunmasıyla
doğrulanır (ekosistem kuralı § 10: çıktının tüketildiği yerden doğrula).
"""
import difflib
import fcntl
import hashlib
import html
import os
import re
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta

import analiz
import cekirdek as c
import degisiklik as dg
import motor

SITE = os.path.join(motor.KOK, "yayin")
YAYIN_DURUM = os.path.join(motor.KOK, "kayit", "yayin-durum.json")
ACIL_NABIZ = os.path.join(motor.KOK, "kayit", "acil-nabiz.json")
KILIT = os.path.join(motor.KOK, "kayit", ".is-kilidi")
YAYIN_KOK = "https://mevzuat-ozet.vercel.app"
VERCEL = os.path.expanduser("~/.npm-global/bin/vercel")
ACIL_SAATLER = (7, 10, 13, 16, 19, 22)      # com.mevzuat.acil.plist ile aynı olmalı

e = html.escape
SIDDET_ADI = {"kritik": "KRİTİK", "onemli": "ÖNEMLİ", "bilgi": "bilgi"}


# ─────────────────────────────────────────────────── kilit
@contextmanager
def is_kilidi(bekle=True, sure=1800):
    """Günlük iş ile acil iş aynı anda durum.json / gunluk.json yazmasın.
    bekle=False: kilit doluysa hemen None döner (acil iş atlar, günlük kapsar)."""
    os.makedirs(os.path.dirname(KILIT), exist_ok=True)
    f = open(KILIT, "w")
    basla = time.time()
    while True:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if not bekle or time.time() - basla > sure:
                f.close()
                yield None
                return
            time.sleep(5)
    try:
        yield f
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


# ─────────────────────────────────────────────────── metin → HTML
def _sade(t):
    """pdftotext -layout sütun boşluklarını tek boşluğa indirir, satırları korur."""
    return "\n".join(re.sub(r"[ \t]{2,}", " ", x).strip() for x in t.splitlines()).strip()


def kelime_farki_html(eski, yeni, baglam=8):
    """Kelime düzeyinde fark: <del>silinen</del> <ins>eklenen</ins>.
    autojunk=False ZORUNLU (bkz. mevzuat.kelime_farki): mevzuat metninde sık
    kelimeler ('ve', 'madde') junk sayılırsa fark anlamsızlaşır."""
    a, b = eski.split(), yeni.split()
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    parca = []
    for etiket, i1, i2, j1, j2 in sm.get_opcodes():
        if etiket == "equal":
            p = a[i1:i2]
            if len(p) > 2 * baglam:
                parca.append(e(" ".join(p[:baglam])) + ' <span class="atla">…</span> '
                             + e(" ".join(p[-baglam:])))
            else:
                parca.append(e(" ".join(p)))
        else:
            if i1 != i2:
                parca.append(f"<del>{e(' '.join(a[i1:i2]))}</del>")
            if j1 != j2:
                parca.append(f"<ins>{e(' '.join(b[j1:j2]))}</ins>")
    return " ".join(x for x in parca if x)


# ─────────────────────────────────────────────────── kartlar
def _rozet(siddet):
    return f'<span class="rozet {e(siddet)}">{e(SIDDET_ADI.get(siddet, siddet))}</span>'


def _olay_karti(k, olay, dur, acil_zamani=""):
    """Madde olayı kartı. YALNIZ resmî metin ve künye — `neden`, `not`,
    `kaynak`, etki ve dosya yolları buraya GİRMEZ (bkz. modül başı)."""
    slug, madde = k["slug"], str(olay.get("madde") or "")
    ad = olay.get("ad", slug)
    b = [f'<article class="kart {e(k["siddet"])}" id="{e(k["kimlik"])}">',
         f'<div class="ust">{_rozet(k["siddet"])} <span class="tarih">tespit '
         f'{e(olay.get("tarih", ""))}</span>'
         + (f' <span class="acil">acil bildirildi {e(acil_zamani)}</span>' if acil_zamani else "")
         + "</div>",
         f"<h3>{e(ad)}{' · madde ' + e(madde) if madde else ''}</h3>",
         f'<p class="tur">{e(olay.get("tur_adi", ""))}'
         + (" · ★ kritik madde" if k.get("kritik_madde") else "") + "</p>",
         f'<p class="ozet">{e(olay.get("ozet", ""))}</p>']
    if olay.get("kunye"):
        b.append(f'<p class="kunye">{e(olay["kunye"])}</p>')
    if dur.get("sayfa_url"):
        b.append(f'<p class="link"><a href="{e(dur["sayfa_url"])}" target="_blank" '
                 f'rel="noopener">mevzuat.gov.tr\'de belgeyi aç ↗</a></p>')

    yeni_yol = os.path.join(motor.MET_DIR, slug + ".txt")
    if madde and os.path.exists(yeni_yol):
        with open(yeni_yol, encoding="utf-8") as f:
            yeni = f.read()
        fyol = dg.fark_dosyasi(olay)
        eski = None
        if fyol:
            with open(fyol, encoding="utf-8") as f:
                eski, _ = dg.eski_nusha(slug, f.read(), yeni)
        y_m = dg.madde_metni(yeni, madde)
        e_m = dg.madde_metni(eski, madde) if eski else None
        if e_m and y_m and e_m != y_m:
            b.append("<h4>Ne değişti</h4>")
            b.append(f'<div class="fark">{kelime_farki_html(_sade(e_m), _sade(y_m))}</div>')
            b.append('<p class="aciklama"><del>silinen</del> · <ins>eklenen</ins></p>')
            b.append(f"<details><summary>Eski metin</summary><pre>{e(_sade(e_m))}</pre></details>")
        elif not e_m and y_m:
            b.append('<p class="aciklama">Değişiklik öncesi metin bu sistemde yok '
                     '(izleme 19.09.2026\'da başladı) — yalnız güncel metin gösteriliyor.</p>')
        if y_m:
            b.append(f"<details><summary>Güncel metin (mevzuat.gov.tr, son doğrulama "
                     f"{e(dur.get('son_dogrulama', '?'))})</summary><pre>{e(_sade(y_m))}</pre></details>")
        elif e_m:
            b.append("<p>Madde güncel metinde yok — metinden kaldırılmış.</p>")
            b.append(f"<details><summary>Kaldırılan metin</summary><pre>{e(_sade(e_m))}</pre></details>")
    b.append("</article>")
    return "\n".join(b)


def _izlenen_ad(sebep, kaynak):
    """'izlenen: y-uzaktan-calisma' → belgenin adı (slug sayfada anlamsız)."""
    ad = {m["slug"]: m["ad"] for m in kaynak.get("mevzuat", [])}
    return re.sub(r"izlenen: ([\w-]+)(?: \(no\))?",
                  lambda m: f"izlenen belge: {ad.get(m.group(1), m.group(1))}", sebep)


def _rg_karti(k, kaynak, durum_json, olaylar, acil_zamani=""):
    b = [f'<article class="kart {e(k["siddet"])}" id="{e(k["kimlik"])}">',
         f'<div class="ust">{_rozet(k["siddet"])} <span class="tarih">Resmî Gazete '
         f'{e(k["tarih"])}</span>'
         + (f' <span class="acil">acil bildirildi {e(acil_zamani)}</span>' if acil_zamani else "")
         + "</div>",
         f"<h3>{e(k['baslik'])}</h3>",
         f'<p class="tur">{e(_izlenen_ad(k["ozet"], kaynak))}</p>']
    rec = None
    try:
        rec = dg.rg_kaydi(k)
    except Exception as ex:
        b.append(f'<p class="aciklama">Fihrist kaydına ulaşılamadı: {e(str(ex))}</p>')
    linkler = []
    if rec:
        linkler.append(f'<a href="{e(rec["url"])}" target="_blank" rel="noopener">'
                       f'Resmî Gazete\'de aç (sayı {e(str(rec.get("sayi", "")))}) ↗</a>')
    if k.get("slug"):
        d = durum_json.get(k["slug"], {})
        if d.get("sayfa_url"):
            linkler.append(f'<a href="{e(d["sayfa_url"])}" target="_blank" rel="noopener">'
                           f'mevzuat.gov.tr\'de belgeyi aç ↗</a>')
    if linkler:
        b.append('<p class="link">' + " · ".join(linkler) + "</p>")
    if k.get("slug"):
        sonra = [x for x in olaylar if x.get("slug") == k["slug"]
                 and x.get("zaman", "") >= k["rg_tarih"]]
        if sonra:
            b.append('<p class="durum ok">mevzuat.gov.tr metnine işlendi: '
                     + "; ".join(e(x.get("ozet", "")) for x in sonra[:4]) + "</p>")
        else:
            b.append('<p class="durum">mevzuat.gov.tr metnine henüz işlenmedi '
                     '(konsolidasyon gün(ler) sürer; işlendiği gün madde değişikliği olarak gelir).</p>')
    if rec:
        try:
            metin, yontem = dg.rg_belge_metni(rec["url"])
            if metin:
                b.append(f"<details><summary>Resmî Gazete metni"
                         f"{' (OCR — sayıları kaynakla karşılaştırın)' if yontem.startswith('OCR') else ''}"
                         f"</summary><pre>{e(_sade(metin)[:5000])}"
                         f"{'…' if len(metin) > 5000 else ''}</pre></details>")
        except Exception:
            pass
    b.append("</article>")
    return "\n".join(b)


def _aym_tablosu(kalemler):
    if not kalemler:
        return ""
    s = ['<div class="tablo"><table><thead><tr><th></th><th>Tür</th><th>Konu</th>'
         '<th>Sonuç</th><th>Karar</th></tr></thead><tbody>']
    for k in kalemler:
        tur = "norm denetimi" if k["aym"] == "norm" else "bireysel başvuru"
        link = (f'<a href="{e(k["rg_url"])}" target="_blank" rel="noopener">'
                f'{e(dg._kisa_aym(k["baslik"]))} ↗</a>' if k.get("rg_url")
                else e(dg._kisa_aym(k["baslik"])))
        s.append(f'<tr class="{"saglik" if k.get("saglik") else ""}" id="{e(k["kimlik"])}">'
                 f'<td>{"🩺" if k.get("saglik") else ""}</td><td>{e(tur)}</td>'
                 f'<td>{e(k.get("aym_konu", ""))}</td>'
                 f'<td class="sonuc">{e(k.get("aym_isaret", ""))} {e(k.get("aym_sonuc", ""))}</td>'
                 f"<td>{link} · RG {e(k['tarih'])}</td></tr>")
    s.append("</tbody></table></div>")
    s.append(f'<p class="aciklama">{e(dg.ISARET_ACIKLAMA)} · 🩺 konu sağlıkla ilgili · '
             f"Konu ve sonuç karar metninden otomatik çıkarılır (çoğu OCR); "
             f"alıntıdan önce Resmî Gazete metnine bakın.</p>")
    return "\n".join(s)


# ─────────────────────────────────────────────────── sayfa
STIL = """
:root{--zemin:#f7f6f2;--kart:#fff;--yazi:#1d1d1b;--soluk:#6b6a64;--cizgi:#e3e1d9;
--kirmizi:#b3261e;--sari:#9a6b00;--yesil:#1e7a3c;--mavi:#1f5fa8;--del:#fbe3e1;--ins:#dff3e4}
@media (prefers-color-scheme:dark){:root{--zemin:#161614;--kart:#201f1c;--yazi:#ecebe6;
--soluk:#a3a198;--cizgi:#34322d;--kirmizi:#ff8a80;--sari:#f0c060;--yesil:#7fd69b;
--mavi:#8ab8ff;--del:#4a1f1c;--ins:#1c3d27}}
*{box-sizing:border-box}body{margin:0;background:var(--zemin);color:var(--yazi);
font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:860px;margin:0 auto;padding:16px}
h1{font-size:1.45rem;margin:.4rem 0}h2{font-size:1.15rem;margin:1.6rem 0 .6rem;
border-bottom:1px solid var(--cizgi);padding-bottom:.3rem}h3{font-size:1.05rem;margin:.3rem 0}
h4{font-size:.95rem;margin:.8rem 0 .3rem}
.alt{color:var(--soluk);font-size:.9rem;margin:0}
.ozet-kutu{background:var(--kart);border:1px solid var(--cizgi);border-radius:10px;
padding:12px 14px;margin:12px 0}.ozet-kutu.temiz{border-left:4px solid var(--yesil)}
.ozet-kutu.var{border-left:4px solid var(--kirmizi)}
.uyari{background:var(--kart);border-left:4px solid var(--sari);padding:10px 14px;
border-radius:8px;margin:8px 0}
.kart{background:var(--kart);border:1px solid var(--cizgi);border-radius:10px;
padding:12px 14px;margin:12px 0}.kart.kritik{border-left:4px solid var(--kirmizi)}
.kart.onemli{border-left:4px solid var(--sari)}
.ust{font-size:.82rem;color:var(--soluk);display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.rozet{font-weight:700;font-size:.72rem;padding:1px 7px;border-radius:99px;border:1px solid}
.rozet.kritik{color:var(--kirmizi)}.rozet.onemli{color:var(--sari)}.rozet.bilgi{color:var(--soluk)}
.acil{color:var(--kirmizi);font-weight:600}
.tur{color:var(--soluk);margin:.1rem 0 .4rem;font-size:.92rem}.kunye{font-size:.88rem;color:var(--soluk)}
.link a{color:var(--mavi);font-weight:600;text-decoration:none}.link a:hover{text-decoration:underline}
.fark{background:var(--zemin);border-radius:8px;padding:10px;font-size:.93rem;overflow-wrap:anywhere}
del{background:var(--del);text-decoration:line-through}ins{background:var(--ins);text-decoration:none}
.atla{color:var(--soluk)}.aciklama{font-size:.82rem;color:var(--soluk)}
.durum{font-size:.88rem;color:var(--sari)}.durum.ok{color:var(--yesil)}
details{margin:.4rem 0}summary{cursor:pointer;color:var(--mavi);font-size:.9rem}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.5 ui-monospace,Menlo,monospace;
background:var(--zemin);padding:10px;border-radius:8px;max-height:60vh;overflow:auto}
.tablo{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.88rem;background:var(--kart)}
th,td{border:1px solid var(--cizgi);padding:6px 8px;vertical-align:top;text-align:left}
tr.saglik td{background:var(--ins)}td.sonuc{white-space:nowrap}
a{color:var(--mavi)}footer{margin:2rem 0 1rem;font-size:.8rem;color:var(--soluk)}
ul.arsiv{padding-left:1.1rem}
"""


def _sayfa(baslik, govde, kimlik, geri=True):
    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<meta name="yayin-kimligi" content="{e(kimlik)}">
<title>{e(baslik)}</title><style>{STIL}</style></head>
<body><main>
{govde}
<footer>{'<a href="/">← tüm özetler</a> · ' if geri else ''}Kaynak: mevzuat.gov.tr konsolide
metinleri ve Resmî Gazete. Bu sayfa otomatik üretilir, hukuki görüş değildir; alıntı
yapmadan önce resmî metne bakın. Yayın {e(kimlik)}</footer>
</main></body></html>
"""


def _bolumler(kalemler, acil_bilgisi=None, sayfa_turu="gunluk"):
    """Kalemleri üç bölüme dağıtır ve HTML döndürür."""
    acil_bilgisi = acil_bilgisi or {}
    kaynak = c.yukle(motor.KAYNAK, {"mevzuat": []})
    durum_json = c.yukle(motor.DURUM)
    olaylar = c.yukle(motor.GUNLUK, {"olaylar": []})["olaylar"]
    olay_id = {o.get("id"): o for o in olaylar}

    madde = [k for k in kalemler if k["kaynak"] == "mevzuat"]
    rg_ = [k for k in kalemler if k["kaynak"] == "rg" and not k.get("aym")]
    aym = [k for k in kalemler if k.get("aym")]
    s = []
    if madde:
        s.append(f"<h2>Madde değişiklikleri ({len(madde)})</h2>")
        for k in madde:
            o = olay_id.get(k["kimlik"])
            if o:
                s.append(_olay_karti(k, o, durum_json.get(k["slug"], {}),
                                     acil_bilgisi.get(k["kimlik"], "")))
    if rg_:
        s.append(f"<h2>Resmî Gazete ({len(rg_)})</h2>")
        for k in rg_:
            s.append(_rg_karti(k, kaynak, durum_json, olaylar, acil_bilgisi.get(k["kimlik"], "")))
    if aym:
        s.append(f"<h2>Anayasa Mahkemesi kararları ({len(aym)})</h2>")
        s.append(_aym_tablosu(aym))
    return "\n".join(s), (madde, rg_, aym)


def _yayin_kimligi(kalemler):
    h = hashlib.sha256("|".join(k["kimlik"] for k in kalemler).encode()).hexdigest()[:6]
    return f"{datetime.now():%Y%m%d-%H%M%S}-{h}"


def _yaz(yol, icerik):
    tam = os.path.join(SITE, yol)
    os.makedirs(os.path.dirname(tam), exist_ok=True)
    with open(tam, "w", encoding="utf-8") as f:
        f.write(icerik)


def _vercel_json():
    _yaz("vercel.json", '{\n  "cleanUrls": true,\n  "trailingSlash": false,\n'
         '  "headers": [{"source": "/(.*)", "headers": [\n'
         '    {"key": "X-Robots-Tag", "value": "noindex, nofollow"},\n'
         '    {"key": "Cache-Control", "value": "public, max-age=0, must-revalidate"}]}]\n}\n')


def _index(durum):
    sayfalar = sorted(durum.get("sayfalar", []), key=lambda x: x["zaman"], reverse=True)
    son_gunluk = next((x for x in sayfalar if x["tur"] == "gunluk"), None)
    s = ["<h1>Mevzuat değişiklik özetleri</h1>",
         '<p class="alt">İzlenen kanun ve yönetmeliklerdeki değişiklikler — günlük özet '
         'her sabah, acil bildirim seçili belgelerde değişiklik görüldüğünde.</p>']
    if son_gunluk:
        s.append(f'<p class="link"><a href="/{e(son_gunluk["yol"][:-5])}">Son günlük özet: '
                 f'{e(son_gunluk["baslik"])} →</a></p>')
    s.append('<h2>Arşiv</h2><ul class="arsiv">')
    for x in sayfalar[:90]:
        im = "🚨" if x["tur"] == "acil" else "📋"
        s.append(f'<li>{im} <a href="/{e(x["yol"][:-5])}">{e(x["baslik"])}</a> '
                 f'<span class="alt">· {e(x.get("ozet", ""))}</span></li>')
    s.append("</ul>")
    _yaz("index.html", _sayfa("Mevzuat değişiklik özetleri", "\n".join(s),
                              durum.get("son_kimlik", ""), geri=False))


def _sayfa_kaydi(durum, yol, tur, baslik, ozet):
    durum["sayfalar"] = [x for x in durum.get("sayfalar", []) if x["yol"] != yol]
    durum["sayfalar"].append({"yol": yol, "tur": tur, "baslik": baslik, "ozet": ozet,
                              "zaman": datetime.now().isoformat(timespec="seconds")})


# ─────────────────────────────────────────────────── yayınla + doğrula
def yayinla():
    """yayin/ klasörünü Vercel'e production olarak yükler -> (ok, mesaj)."""
    if not os.path.exists(os.path.join(SITE, ".vercel", "project.json")):
        return False, "yayin/.vercel/project.json yok — `vercel link --project mevzuat-ozet`"
    if not os.path.exists(VERCEL):
        return False, f"vercel CLI yok: {VERCEL}"
    ortam = dict(os.environ, PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:"
                 + os.environ.get("PATH", ""))
    try:
        r = subprocess.run([VERCEL, "deploy", "--prod", "--yes"], cwd=SITE, env=ortam,
                           capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return False, "vercel deploy 600 sn'de bitmedi"
    if r.returncode != 0:
        return False, f"vercel deploy çıkış {r.returncode}: {(r.stderr or r.stdout).strip()[-300:]}"
    adres = re.findall(r"https://[\w.-]+\.vercel\.app", r.stdout + r.stderr)
    return True, f"vercel deploy tamam ({adres[0] if adres else 'adres çıktıda yok'})"


def dogrula(yol, kimlik, deneme=8):
    """Canlı sayfada bu yayının kimliği görünüyor mu? '200 OK' yetmez: eski
    sürüm de 200 döner. -> (ok, mesaj)"""
    url = f"{YAYIN_KOK}/{yol}?v={kimlik}"
    son = ""
    for i in range(deneme):
        try:
            istek = urllib.request.Request(url, headers={"User-Agent": c.UA,
                                                         "Cache-Control": "no-cache"})
            with urllib.request.urlopen(istek, timeout=30) as y:
                govde = y.read().decode("utf-8", "replace")
                if y.status == 200 and f'content="{kimlik}"' in govde:
                    return True, f"{YAYIN_KOK}/{yol} · HTTP 200 · yayın {kimlik} canlıda"
                son = f"HTTP {y.status}, yayın kimliği sayfada yok"
        except Exception as ex:
            son = f"{type(ex).__name__}: {ex}"
        time.sleep(4 + 2 * i)
    return False, f"{url} doğrulanamadı — {son}"


# ─────────────────────────────────────────────────── acil nabzı
def acil_nabzi():
    """Acil kontrolün son koşuları -> (son_kosu_metni, uyari|None).
    Günlük özet bunu gösterir: acil iş sessizce durursa ertesi sabah görünür."""
    n = c.yukle(ACIL_NABIZ, {"kosular": []}).get("kosular", [])
    if not n:
        return "henüz koşmadı", None
    son = datetime.fromisoformat(n[-1]["zaman"])
    gun = [x for x in n if datetime.fromisoformat(x["zaman"]) > datetime.now() - timedelta(days=1)]
    metin = (f"son koşu {son:%d.%m %H:%M} ({n[-1].get('sonuc', '?')}) · "
             f"son 24 saatte {len(gun)} koşu")
    uyari = None
    if datetime.now() - son > timedelta(hours=16):
        uyari = f"Acil kontrol {son:%d.%m.%Y %H:%M}'den beri koşmadı (Mac kapalı ya da iş durmuş olabilir)."
    return metin, uyari


# ─────────────────────────────────────────────────── bildirim metni
def bildirim_metni(tur, madde, rg_, aym, uyarilar=()):
    """-> (başlık, gövde). Gövde kısa: ayrıntı sayfada."""
    kritik = [k for k in madde + rg_ if k["siddet"] == "kritik"]
    toplam = len(madde) + len(rg_) + len(aym)
    if tur == "acil":
        baslik = f"🚨 Mevzuat ACİL: {len(madde) + len(rg_)} değişiklik"
    elif uyarilar and not toplam:
        baslik = "⚠️ Mevzuat günlük: inceleme gerekiyor"
    elif kritik:
        baslik = f"🚨 Mevzuat günlük: {toplam} kayıt ({len(kritik)} kritik)"
    elif toplam:
        baslik = f"⚖️ Mevzuat günlük: {toplam} kayıt"
    else:
        baslik = "✅ Mevzuat günlük: değişiklik yok"
    satir = []
    for k in (kritik or madde + rg_)[:4]:
        if k["kaynak"] == "rg":
            satir.append(f"• RG {k['tarih'][:5]}: {k['baslik'][:80]}")
        else:
            ek = f" m.{k['madde']}" if k.get("madde") else ""
            satir.append(f"• {k['baslik'][:40]}{ek} — {k['ozet'][:60]}")
    kalan = len(madde) + len(rg_) - len(satir)
    if kalan > 0:
        satir.append(f"… {kalan} kayıt daha")
    if aym:
        saglik = sum(1 for k in aym if k.get("saglik"))
        ihlal = sum(1 for k in aym if k.get("aym_isaret") == "❗")
        satir.append(f"AYM: {len(aym)} karar" + (f" · {saglik} 🩺" if saglik else "")
                     + (f" · {ihlal} ❗" if ihlal else ""))
    if not toplam and tur == "gunluk":
        satir.append("İzlenen 51 belgede yeni değişiklik yok.")
    for u in uyarilar:
        satir.append(f"⚠ {u[:90]}")
    satir.append("Dokun → özet sayfası")
    return baslik, "\n".join(satir)


# ─────────────────────────────────────────────────── günlük
def gunluk(gonder=True, yayinla_=True, uyarilar=()):
    """Günlük özet sayfası. -> (çıkış kodu, özet metni)
    0 yayın doğrulandı · 2 yayın/doğrulama/bildirim hatası"""
    import bildirim
    uyarilar = list(uyarilar)
    durum = c.yukle(YAYIN_DURUM, {})
    ilk = not durum.get("son_gunluk")
    yayinlanan = set(durum.get("gunluk_yayinlanan", []))
    kalemler = dg.tum_kalemler()
    yeni = [k for k in kalemler if any(a not in yayinlanan for a in k["anahtarlar"])]
    bugun = datetime.now().strftime("%Y-%m-%d")
    # Aynı gün ikinci koşu (elle ya da uyku telafisi) sabah sayfasını
    # SİLMESİN: günün sayfası o gün yayımlanan her şeyin birleşimidir.
    gun_kimlikleri = durum.setdefault("gunler", {}).setdefault(bugun, [])
    for k in yeni:
        if k["kimlik"] not in gun_kimlikleri:
            gun_kimlikleri.append(k["kimlik"])
    harita = {k["kimlik"]: k for k in kalemler}
    sayfa_kalemleri = [harita[x] for x in gun_kimlikleri if x in harita]
    dg.aym_ozetleri([k for k in sayfa_kalemleri if k.get("aym")])

    acil_bilgisi = {}
    for kimlik, zaman in durum.get("acil_bildirilen", {}).items():
        acil_bilgisi[kimlik] = datetime.fromisoformat(zaman).strftime("%d.%m %H:%M")

    son_den, son_rg, tazelik = dg._tazelik()
    uyarilar += tazelik
    nabiz, nabiz_uyari = acil_nabzi()
    if nabiz_uyari:
        uyarilar.append(nabiz_uyari)

    govde, (madde, rg_, aym) = _bolumler(sayfa_kalemleri, acil_bilgisi)
    kimlik = _yayin_kimligi(sayfa_kalemleri)
    gun_adi = datetime.now().strftime("%d.%m.%Y")
    ozet = (f"{len(madde)} madde değişikliği · {len(rg_)} RG kaydı · {len(aym)} AYM kararı"
            if sayfa_kalemleri else "değişiklik yok")
    ust = [f"<h1>Mevzuat günlük özeti · {e(gun_adi)}</h1>",
           f'<p class="alt">Son denetim: mevzuat.gov.tr '
           f"{e(f'{son_den:%d.%m %H:%M}' if son_den else '—')} · Resmî Gazete "
           f"{e(f'{son_rg:%d.%m %H:%M}' if son_rg else '—')} · acil kontrol: {e(nabiz)}</p>"]
    if ilk:
        ust.append('<p class="alt">İlk özet: sistemde kayıtlı bütün değişiklikler listelendi.</p>')
    for u in uyarilar:
        ust.append(f'<div class="uyari">⚠ {e(u)}</div>')
    if sayfa_kalemleri:
        kritik = sum(1 for k in madde + rg_ if k["siddet"] == "kritik")
        ust.append(f'<div class="ozet-kutu var"><b>{e(ozet)}</b>'
                   + (f" · {kritik} kritik" if kritik else "") + "</div>")
    else:
        ust.append('<div class="ozet-kutu temiz"><b>Bugün değişiklik yok.</b> İzlenen 51 '
                   'belgenin hepsi denetlendi; Resmî Gazete tarandı.</div>')
    yol = f"gun/{bugun}.html"
    _yaz(yol, _sayfa(f"Mevzuat günlük özeti · {gun_adi}", "\n".join(ust) + govde, kimlik))
    _sayfa_kaydi(durum, yol, "gunluk", f"Günlük özet · {gun_adi}", ozet)
    durum["son_kimlik"] = kimlik
    _vercel_json()
    _index(durum)

    url = f"{YAYIN_KOK}/{yol[:-5]}"
    rapor, kod = [], 0
    if yayinla_:
        ok, m = yayinla()
        rapor.append(f"yayın: {'✅' if ok else '❌'} {m}")
        if ok:
            ok, m = dogrula(yol[:-5], kimlik)
            rapor.append(f"doğrulama: {'✅' if ok else '❌'} {m}")
        if not ok:
            kod = 2
            uyarilar.append("Özet sayfası yayımlanamadı — ayrıntı kayit/gunluk.log")
            url = None
    if gonder:
        b, g = bildirim_metni("gunluk", madde, rg_, aym, uyarilar)
        ok, ham = bildirim.gonder(b, g, url=url)
        rapor.append(f"bildirim: {'✅' if ok else '❌'} {b} · ham yanıt: {ham}")
        if not ok:
            kod = 2
    # Yayın doğrulanmadıysa kalemler "yayınlandı" sayılmaz: yarınki özet onları
    # yeniden içerir. Önizlemede (yayinla_=False) de durum ilerlemez.
    if yayinla_ and kod == 0:
        for k in yeni:
            yayinlanan.update(k["anahtarlar"])
        durum.update(gunluk_yayinlanan=sorted(yayinlanan),
                     son_gunluk=datetime.now().isoformat(timespec="seconds"))
        c.kaydet(YAYIN_DURUM, durum)
    return kod, "\n".join(rapor) or f"önizleme: {os.path.join(SITE, yol)}"


# ─────────────────────────────────────────────────── acil
def acil(kalemler, gonder=True, deneme=False):
    """Çekirdek belgelerdeki değişiklik için ayrı sayfa + ACİL bildirim.
    deneme=True: uçtan uca sınama — başlık "🧪 DENEME", arşive ve
    "acil bildirildi" kaydına girmez. -> (çıkış kodu, rapor)"""
    import bildirim
    durum = c.yukle(YAYIN_DURUM, {})
    simdi = datetime.now()
    zaman = simdi.strftime("%d.%m %H:%M")
    govde, (madde, rg_, aym) = _bolumler(kalemler, {k["kimlik"]: zaman for k in kalemler}, "acil")
    kimlik = _yayin_kimligi(kalemler)
    on = "🧪 DENEME · " if deneme else ""
    yol = f"acil/{'deneme-' if deneme else ''}{simdi:%Y%m%d-%H%M}.html"
    ozet = f"{len(madde)} madde değişikliği · {len(rg_)} RG kaydı"
    ust = [f"<h1>{on}🚨 Acil mevzuat bildirimi · {e(simdi.strftime('%d.%m.%Y %H:%M'))}</h1>",
           '<p class="alt">Acil listesindeki belgelerde değişiklik görüldü; günlük özeti '
           'beklemeden bildirildi. Aynı kayıtlar yarınki günlük özette de yer alır.</p>']
    if deneme:
        ust.append('<div class="uyari">Bu bir DENEME sayfasıdır: acil bildirim zincirini '
                   '(sayfa → yayın → bildirim) sınamak için son kritik değişiklikle üretildi.</div>')
    ust.append(f'<div class="ozet-kutu var"><b>{e(ozet)}</b></div>')
    _yaz(yol, _sayfa(f"{on}Acil mevzuat bildirimi · {zaman}", "\n".join(ust) + govde, kimlik))
    if not deneme:
        _sayfa_kaydi(durum, yol, "acil", f"Acil · {simdi:%d.%m.%Y %H:%M}", ozet)
    durum["son_kimlik"] = kimlik
    _vercel_json()
    _index(durum)

    rapor, kod, url = [], 0, f"{YAYIN_KOK}/{yol[:-5]}"
    ok, m = yayinla()
    rapor.append(f"yayın: {'✅' if ok else '❌'} {m}")
    if ok:
        ok, m = dogrula(yol[:-5], kimlik)
        rapor.append(f"doğrulama: {'✅' if ok else '❌'} {m}")
    uyarilar = []
    if not ok:
        kod, url = 2, None
        uyarilar.append("Sayfa yayımlanamadı — ayrıntı kayit/acil.log")
    if gonder:
        b, g = bildirim_metni("acil", madde, rg_, aym, uyarilar)
        ok2, ham = bildirim.gonder(on + b, g, url=url, seviye="timeSensitive")
        rapor.append(f"bildirim: {'✅' if ok2 else '❌'} {on}{b} · ham yanıt: {ham}")
        if not ok2:
            kod = 2
    # Bildirim APNs'e ulaştıysa kalemler "acil bildirildi" sayılır — sayfa
    # yayımlanamamış olsa bile (bildirim metni değişikliği zaten taşıyor).
    if not deneme and (not gonder or "✅ " in rapor[-1]):
        ab = durum.setdefault("acil_bildirilen", {})
        for k in kalemler:
            ab[k["kimlik"]] = simdi.isoformat(timespec="seconds")
    c.kaydet(YAYIN_DURUM, durum)
    return kod, "\n".join(rapor)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] not in ("gunluk", "onizle", "dogrula"):
        print(__doc__)
        sys.exit(2)
    if a[0] == "dogrula":
        ok, m = dogrula(a[1], c.yukle(YAYIN_DURUM, {}).get("son_kimlik", ""))
        print(m)
        sys.exit(0 if ok else 2)
    onizle = a[0] == "onizle"
    kod, rapor = gunluk(gonder=not onizle and "--gonderme" not in a,
                        yayinla_=not onizle and "--yayinlama" not in a)
    print(rapor)
    sys.exit(kod)
