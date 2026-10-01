#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mevzuat.py — mevzuat.gov.tr güncellik takibi

    python3 mevzuat.py denetle [slug...] [--kuru]  ★ güncellik denetimi (slug: yalnız onlar)
    python3 mevzuat.py indir [slug...]       ilk kurulum / eksikleri tamamla
    python3 mevzuat.py liste [--sinif X]     izlenen mevzuat tablosu
    python3 mevzuat.py madde <slug> <no>     ★ maddenin LAFZINI bas (alıntı için)
    python3 mevzuat.py fark <slug> [--kelime]  son değişikliğin farkı
    python3 mevzuat.py bul "<ifade>"         ★ külliyatta tam metin arama
    python3 mevzuat.py olaylar [--kritik] [-n N]   değişiklik günlüğü
    python3 mevzuat.py degisiklikler [--kuru|--son]  ★ numaralı rapor (--son: son listeyi yeniden bas)
    python3 mevzuat.py degisiklik <no> [--tam] ★ o numaranın detay paketi (eski/yeni lafız, etki)
    python3 mevzuat.py rg [gün]              Resmî Gazete taraması (ikinci sinyal)
    python3 mevzuat.py etki <slug> <madde>   bu maddeye atıf yapan belgeler
    python3 mevzuat.py ara "<ifade>" [tur]   yeni kayıt için numara çöz
    python3 mevzuat.py durum                 sistem sağlığı

ALTIN KURAL: Hukuk metninin tek kaynağı mevzuat.gov.tr'dir. Bir belgeye madde
numarası, oran, süre ya da nisap yazılacaksa ÖNCE `madde` komutuyla lafzı okunur.
Metne ulaşılamıyorsa uydurulmaz — "ulaşamadım" denir.
"""
import difflib
import os
import re
import subprocess
import sys
from datetime import datetime

import analiz
import cekirdek as c
import motor

C = dict(kir="\033[31m", yes="\033[32m", sar="\033[33m", mav="\033[36m",
         gri="\033[90m", kal="\033[1m", sn="\033[0m") if sys.stdout.isatty() \
    else dict.fromkeys(["kir", "yes", "sar", "mav", "gri", "kal", "sn"], "")

SIMGE = {"ilk": "+", "ayni": "·", "degisti": "!", "hata": "✖"}
RENK = {"ilk": "mav", "ayni": "yes", "degisti": "sar", "hata": "kir"}


def kaynak_yukle():
    return c.kaynak()


# ─────────────────────────────────────────────────── denetle / indir
def _kos(sluglar, kuru, baslik, devre_kesiciyi_atla=False):
    kaynak = kaynak_yukle()
    kayitlar = kaynak["mevzuat"]
    if sluglar:
        kayitlar = [m for m in kayitlar
                    if m["slug"] in sluglar or str(m["no"]) in sluglar]
        if not kayitlar:
            print(f"{C['kir']}Eşleşen kayıt yok.{C['sn']}")
            return 2
    durum = c.yukle(motor.DURUM)
    artik = motor.artiklari_temizle()

    uyari = c.tls_uyarisi()
    print(f"\n{C['kal']}MEVZUAT {baslik}{C['sn']}  ·  {len(kayitlar)} kayıt  ·  "
          f"{datetime.now():%d.%m.%Y %H:%M}" + ("  (KURU — yazma yok)" if kuru else ""))
    if uyari:
        print(f"{C['kir']}⚠ {uyari}{C['sn']}")
    else:
        print(f"{C['gri']}TLS doğrulanıyor (sertifika/mevzuat-ca.pem) · "
              f"pdftotext {c.poppler_surumu()} · istekler arası {c.NEZAKET} sn{C['sn']}")
    if artik:
        print(f"{C['gri']}({artik} yarım kalmış geçici dosya temizlendi){C['sn']}")
    print("─" * 82)

    sonuclar = []
    yazilan = 0
    for i, m in enumerate(kayitlar, 1):
        r = motor.kalem(m, durum, kuru)
        r["arac_surumu"] = c.poppler_surumu()
        sonuclar.append(r)
        renk = C[RENK[r["sonuc"]]]
        satir = (f" {renk}{SIMGE[r['sonuc']]}{C['sn']} [{i:>2}/{len(kayitlar)}] "
                 f"{r['slug']:<27}{r['ad'][:36]}")
        if r["sonuc"] == "hata":
            satir += f"\n      {C['kir']}└ {r['not_']}{C['sn']}"
        elif r["sonuc"] == "degisti":
            satir += (f"\n      {C['sar']}└ DEĞİŞTİ  {r['eski_imza'][:8]} → "
                      f"{r['yeni_imza'][:8]}  ·  {len(r['olaylar'])} olay{C['sn']}")
            for o in r["olaylar"][:6]:
                im = "🔴" if o["siddet"] == "kritik" else "🟡"
                satir += f"\n         {im} {o['ozet'][:72]}"
            if len(r["olaylar"]) > 6:
                satir += f"\n         {C['gri']}… {len(r['olaylar'])-6} olay daha{C['sn']}"
        elif r["sonuc"] == "ilk":
            satir += (f"  {C['mav']}({r['sayfa']} s. · {r['karakter']//1000}k · "
                      f"{r['madde']} madde){C['sn']}")
        elif r.get("yol") == "304":
            satir += f"  {C['gri']}(304 — sunucu değişmedi dedi){C['sn']}"
        if r.get("mukerrer"):
            satir += (f"\n      {C['sar']}└ ⚠ belirsiz: {len(r['mukerrer'])} mükerrer "
                      f"madde anahtarı ({', '.join(r['mukerrer'][:4])}){C['sn']}")
        print(satir, flush=True)

        # ARTIMLI KAYIT: ilk indirme sonuçları HEMEN yazılır.
        # Karşılaştırılacak eski nüsha olmadığı için devre kesiciyi
        # ilgilendirmez (kesici yalnız degisti/ayni oranına bakar) ve koşu
        # yarıda kesilirse ilerleme kaybolmaz — 19.09.2026'da 42/45'te
        # kesilen koşuda tam olarak bu yaşandı.
        if not kuru and r["sonuc"] == "ilk":
            motor.yaz(m, r, durum)
            yazilan += 1
            if yazilan % 5 == 0:
                c.kaydet(motor.DURUM, durum)
    if not kuru and yazilan:
        c.kaydet(motor.DURUM, durum)

    d = [r for r in sonuclar if r["sonuc"] == "degisti"]
    h = [r for r in sonuclar if r["sonuc"] == "hata"]
    ilk = [r for r in sonuclar if r["sonuc"] == "ilk"]
    ayni = [r for r in sonuclar if r["sonuc"] == "ayni"]
    print("─" * 82)
    print(f" {len(ayni)} değişmemiş · {len(ilk)} yeni · "
          f"{C['sar']}{len(d)} DEĞİŞTİ{C['sn']} · {C['kir']}{len(h)} ulaşılamadı{C['sn']}")

    # ── Ö-9: devre kesici ──
    tetik, mesaj = motor.devre_kesici(sonuclar)
    if tetik and not devre_kesiciyi_atla:
        print(f"\n{C['kir']}{C['kal']}⛔ DEVRE KESİCİ{C['sn']}\n    {mesaj}")
        return 3

    if kuru:
        print(f"{C['gri']}Kuru koşu — hiçbir dosya yazılmadı.{C['sn']}")
        return 1 if (d or h) else 0

    # "ilk" olanlar döngü içinde yazıldı; burada yalnız DEĞİŞENLER yazılır —
    # onlar devre kesici geçtikten sonra işlenmelidir.
    for m, r in zip(kayitlar, sonuclar):
        if r["sonuc"] == "degisti":
            motor.yaz(m, r, durum)
    damga = motor.dogrulamayi_isle(durum, sonuclar)
    c.kaydet(motor.DURUM, durum)
    if damga:
        print(f"{C['gri']}{damga} değişmemiş kaydın son doğrulama damgası "
              f"güncellendi{C['sn']}")

    # Olayları günlüğe yaz
    kayit = []
    for r in sonuclar:
        if r["sonuc"] != "degisti":
            continue
        temel = {"slug": r["slug"], "ad": r["ad"], "sinif": r["sinif"],
                 "kaynak": "mevzuat.gov.tr",
                 "fark_dosyasi": r.get("fark_dosyasi", ""),
                 "fark_satir": r.get("fark_satir", 0)}
        if r["olaylar"]:
            for o in r["olaylar"]:
                kayit.append({**temel, **o})
        else:
            kayit.append({**temel, "tur": "metin_degisti",
                          "tur_adi": analiz.OLAY_ADI["metin_degisti"],
                          "siddet": "bilgi", "madde": "",
                          "ozet": "metin değişti, madde envanteri aynı "
                                  "(dizgi/dipnot oynaması olabilir)"})
    # Ö-6: dayanağı değişen yönetmelikler için uyarı olayı.
    # Bir kanun değiştiğinde ona dayanan yönetmelik çoğu zaman peşinden gelir;
    # bunu beklemek yerine işaretleyip izlemeyi sıkılaştırmak gerekir.
    degisen_slug = {r["slug"] for r in d}
    for m in kaynak_yukle()["mevzuat"]:
        ortak = degisen_slug & set(m.get("dayanak", []))
        if ortak:
            kayit.append({
                "slug": m["slug"], "ad": m["ad"], "sinif": m["sinif"],
                "kaynak": "dayanak-zinciri", "tur": "dayanak_degisti",
                "tur_adi": "dayanağı değişti", "siddet": "onemli", "madde": "",
                "ozet": (f"Dayanağı olan {', '.join(sorted(ortak))} değişti — "
                         f"bu yönetmelik de yakında değişebilir, izlemeyi sıkılaştır."),
            })

    if kayit:
        motor.gunluge_yaz(kayit)
        kritik = [k for k in kayit if k["siddet"] == "kritik"]
        print(f"\n{C['sar']}{C['kal']}⚠ {len(kayit)} olay günlüğe yazıldı"
              f"{C['sn']} ({len(kritik)} kritik). İncelemek için:")
        for r in d:
            print(f"   python3 mevzuat.py fark {r['slug']} --kelime")
    if h:
        print(f"\n{C['kir']}Ulaşılamayanların depodaki nüshası KORUNDU — bayat "
              f"olabilir. Alıntı yapmadan önce tek tek dene:{C['sn']}")
        for r in h:
            print(f"   python3 mevzuat.py indir {r['slug']}")
    return 1 if (d or h) else 0


# ─────────────────────────────────────────────────── fark (Ö-3)
def kelime_farki(eski, yeni):
    """Kelime düzeyinde redline.

    `autojunk=False` ZORUNLUDUR: varsayılan True, uzun metinlerde çok tekrar
    eden token'ları 'junk' sayıp eşleştirmeden çıkarır — mevzuat metninde bu
    tam olarak 've', 'madde', 'fıkra', 'bu' demektir ve fark anlamsızlaşır.
    """
    a, b = eski.split(), yeni.split()
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    parca = []
    for etiket, i1, i2, j1, j2 in sm.get_opcodes():
        if etiket == "equal":
            p = a[i1:i2]
            if len(p) > 12:      # değişmeyen uzun blokları kısalt
                parca.append(" ".join(p[:6]) + f" {C['gri']}…{C['sn']} " + " ".join(p[-6:]))
            else:
                parca.append(" ".join(p))
        else:
            if i1 != i2:
                parca.append(f"{C['kir']}[-{' '.join(a[i1:i2])}-]{C['sn']}")
            if j1 != j2:
                parca.append(f"{C['yes']}{{+{' '.join(b[j1:j2])}+}}{C['sn']}")
    return " ".join(x for x in parca if x)


def komut_fark(slug, kelime=False):
    farklar = sorted(f for f in os.listdir(motor.ARS_DIR)
                     if f.startswith(slug + "_") and f.endswith("_fark.diff"))
    if not farklar:
        print(f"{slug} için kayıtlı fark yok — hiç değişmemiş ya da hiç indirilmemiş.")
        return 2
    yol = os.path.join(motor.ARS_DIR, farklar[-1])
    print(f"{C['kal']}{os.path.relpath(yol, motor.KOK)}{C['sn']}\n")

    if not kelime:
        with open(yol, encoding="utf-8") as f:
            for s in f:
                r = (C["yes"] if s.startswith("+") else C["kir"] if s.startswith("-")
                     else C["mav"] if s.startswith("@@") else "")
                print(r + s.rstrip() + (C["sn"] if r else ""))
        print(f"\n{C['gri']}Kelime düzeyinde görmek için: "
              f"python3 mevzuat.py fark {slug} --kelime{C['sn']}")
        return 0

    # --kelime: diff bloklarını kelime düzeyinde yeniden çıkar
    with open(yol, encoding="utf-8") as f:
        satirlar = f.read().splitlines()
    blok, eski, yeni = [], [], []

    def dok():
        if eski or yeni:
            blok.append((("\n".join(eski)).strip(), ("\n".join(yeni)).strip()))
        eski.clear()
        yeni.clear()

    for s in satirlar:
        if s.startswith(("+++", "---")):
            continue
        if s.startswith("@@"):
            dok()
            blok.append(("@@", s))
        elif s.startswith("-"):
            eski.append(s[1:])
        elif s.startswith("+"):
            yeni.append(s[1:])
        else:
            dok()
    dok()

    n = 0
    for a, b in blok:
        if a == "@@":
            print(f"{C['mav']}{b}{C['sn']}")
            continue
        if not a and not b:
            continue
        n += 1
        print(kelime_farki(a, b))
        print()
    print(f"{C['gri']}{n} değişiklik bloğu · "
          f"{C['kir']}[-silinen-]{C['sn']}{C['gri']} · "
          f"{C['yes']}{{+eklenen+}}{C['sn']}")
    return 0


# ─────────────────────────────────────────────────── bul (Ö-5)
def komut_bul(ifade, sinir=40):
    """Külliyatta tam metin arama; sonucu MADDE numarasıyla birlikte verir."""
    durum = c.yukle(motor.DURUM)
    kaynak = {m["slug"]: m for m in kaynak_yukle()["mevzuat"]}
    try:
        desen = re.compile(ifade, re.IGNORECASE)
    except re.error:
        desen = re.compile(re.escape(ifade), re.IGNORECASE)

    bulundu = 0
    print(f"\n{C['kal']}“{ifade}”{C['sn']} — külliyatta arama\n" + "─" * 82)
    for slug in sorted(os.listdir(motor.MET_DIR)):
        if not slug.endswith(".txt"):
            continue
        s = slug[:-4]
        yol = os.path.join(motor.MET_DIR, slug)
        with open(yol, encoding="utf-8") as f:
            metin = f.read()
        if not desen.search(metin):
            continue
        env = (durum.get(s) or {}).get("envanter") or {}
        sinirlar = sorted(((v["satir"], k) for k, v in env.items()))
        ad = kaynak.get(s, {}).get("ad", s)
        basliklar = []
        for m in desen.finditer(metin):
            satir = metin.count("\n", 0, m.start()) + 1
            madde = ""
            for sn, k in sinirlar:
                if sn <= satir:
                    madde = k
                else:
                    break
            bas = max(0, m.start() - 60)
            baglam = re.sub(r"\s+", " ", metin[bas:m.end() + 60]).strip()
            basliklar.append((madde, satir, baglam, m.group(0)))
            if len(basliklar) >= 4:
                break
        bulundu += 1
        print(f"{C['kal']}{ad}{C['sn']} {C['gri']}({s}){C['sn']}")
        for madde, satir, baglam, esl in basliklar:
            yer = f"m.{madde}" if madde else f"satır {satir}"
            vurgu = baglam.replace(esl, f"{C['sar']}{esl}{C['sn']}")
            print(f"   {C['mav']}{yer:<12}{C['sn']} …{vurgu}…")
        toplam = len(desen.findall(metin))
        if toplam > len(basliklar):
            print(f"   {C['gri']}… bu belgede toplam {toplam} geçiş{C['sn']}")
        print()
        if bulundu >= sinir:
            break
    if not bulundu:
        print("Sonuç yok.")
    else:
        print("─" * 82)
        print(f"{bulundu} belgede bulundu. Lafzı okumak için: "
              f"python3 mevzuat.py madde <slug> <no>")
    return 0 if bulundu else 2


# ─────────────────────────────────────────────────── madde
def komut_madde(slug, istenen):
    yol = os.path.join(motor.MET_DIR, slug + ".txt")
    if not os.path.exists(yol):
        print(f"{C['kir']}{slug} indirilmemiş. Önce: "
              f"python3 mevzuat.py indir {slug}{C['sn']}")
        return 2
    with open(yol, encoding="utf-8") as f:
        metin = f.read()
    d = c.yukle(motor.DURUM).get(slug, {})
    env = d.get("envanter") or {}

    it = istenen.strip()
    anahtar = None
    for aday in (it, it.title(), it.capitalize()):
        if aday in env:
            anahtar = aday
            break
    if anahtar is None:
        norm = re.sub(r"\s+", " ", it).strip()
        for k in env:
            if c_kucult(k) == c_kucult(norm):
                anahtar = k
                break
    if anahtar is None:
        yakin = difflib.get_close_matches(it, list(env), n=5, cutoff=0.5)
        print(f"{C['kir']}{slug} içinde “{it}” maddesi yok.{C['sn']}"
              + (f"\nBunu mu demek istedin: {', '.join(yakin)}" if yakin else ""))
        return 2

    bilgi = env[anahtar]
    son = analiz.govde_siniri(metin)
    govde = metin[:son]
    isaret = list(analiz.MADDE.finditer(govde))
    hedef = None
    for i, m in enumerate(isaret):
        satir = govde.count("\n", 0, m.start()) + 1
        if satir == bilgi["satir"]:
            hedef = (m.start(), isaret[i + 1].start() if i + 1 < len(isaret) else son)
            break
    if hedef is None:
        print(f"{C['kir']}Envanter ile metin uyuşmuyor — `denetle` çalıştır.{C['sn']}")
        return 2

    durum_im = {"yururlukte": C["yes"] + "yürürlükte",
                "mulga": C["kir"] + "MÜLGA",
                "iptal": C["kir"] + "ANAYASA MAHKEMESİ'NCE İPTAL",
                "yurutme_durduruldu": C["kir"] + "YÜRÜTMESİ DURDURULDU"}[bilgi["durum"]]
    print(f"\n{C['kal']}{d.get('ad', slug)}{C['sn']}  ·  madde {anahtar}  ·  "
          f"{durum_im}{C['sn']}")
    if bilgi.get("kunye"):
        print(f"{C['sar']}{bilgi['kunye']}{C['sn']}")
    print(f"{C['gri']}{d.get('sayfa_url','')}\n"
          f"son doğrulama: {d.get('son_dogrulama','?')} · "
          f"imza({d.get('imza_turu','?')}): {d.get('imza','')[:12]}{C['sn']}")
    print("─" * 82)
    print(re.sub(r"\n{3,}", "\n\n", govde[hedef[0]:hedef[1]]).rstrip())
    print("─" * 82)
    if bilgi.get("dipnot_blok"):
        print(f"{C['gri']}Dipnotlar (gövdeden ayrıldı — Ö-10):{C['sn']}")
        for x in bilgi["dipnot_blok"]:
            print(f"  {C['gri']}· {x[:150]}{C['sn']}")
    print(f"{C['mav']}Kaynak: {d.get('url','')}{C['sn']}")
    return 0


def c_kucult(s):
    return s.replace("I", "ı").replace("İ", "i").lower()


# ─────────────────────────────────────────────────── liste / olaylar / durum
def komut_liste(sinif=None, grup=None):
    kaynak = kaynak_yukle()["mevzuat"]
    durum = c.yukle(motor.DURUM)
    if sinif:
        kaynak = [m for m in kaynak if m["sinif"] == sinif]
    if grup:
        kaynak = [m for m in kaynak if grup in m.get("grup", [])]
    print(f"\n{C['kal']}{'':2}{'SLUG':<27}{'NO':>10}  {'SINIF':<9}{'MADDE':>6}"
          f"{'SAYFA':>6}  {'SON DOĞRULAMA':<17}{'SON DEĞİŞİKLİK':<15}AD{C['sn']}")
    print("─" * 128)
    for m in kaynak:
        d = durum.get(m["slug"], {})
        im = (C["yes"] + "·" + C["sn"]) if d else (C["kir"] + "✖" + C["sn"])
        ozet = d.get("madde_ozeti") or {}
        ek = ""
        if ozet.get("yurutme_durduruldu"):
            ek = f" {C['kir']}YD:{ozet['yurutme_durduruldu']}{C['sn']}"
        elif ozet.get("iptal"):
            ek = f" {C['sar']}iptal:{ozet['iptal']}{C['sn']}"
        print(f"{im} {m['slug']:<27}{str(m['no']):>10}  {m['sinif']:<9}"
              f"{d.get('madde','—'):>6}{d.get('sayfa','—'):>6}  "
              f"{d.get('son_dogrulama','İNDİRİLMEDİ'):<17}"
              f"{d.get('son_degisiklik','—'):<15}{m['ad'][:30]}{ek}")
    print("─" * 128)
    var = sum(1 for m in kaynak if m["slug"] in durum)
    print(f"{len(kaynak)} kayıt · {var} indirilmiş · "
          f"{sum((durum.get(m['slug']) or {}).get('madde', 0) for m in kaynak)} madde")
    return 0


def komut_olaylar(kritik=False, n=30, slug=None):
    g = c.yukle(motor.GUNLUK, {"olaylar": []})
    ol = g["olaylar"]
    if kritik:
        ol = [o for o in ol if o.get("siddet") == "kritik"]
    if slug:
        ol = [o for o in ol if o.get("slug") == slug]
    ol = ol[-n:]
    if not ol:
        print("Kayıtlı olay yok.")
        return 0
    print(f"\n{C['kal']}DEĞİŞİKLİK GÜNLÜĞÜ{C['sn']} · son {len(ol)} olay\n" + "─" * 82)
    for o in ol:
        im = {"kritik": C["kir"] + "🔴", "onemli": C["sar"] + "🟡",
              "bilgi": C["gri"] + "⚪"}.get(o.get("siddet"), "")
        okundu = "" if o.get("okundu") else f" {C['mav']}●{C['sn']}"
        print(f"{im}{C['sn']} {o.get('tarih','')}  {C['kal']}{o.get('ad','')[:44]}{C['sn']}{okundu}")
        print(f"     {o.get('ozet','')}")
        if o.get("kunye"):
            print(f"     {C['gri']}{o['kunye'][:96]}{C['sn']}")
    print("─" * 82)
    print(f"{C['gri']}Tümü: arayüz http://127.0.0.1:3031/gunluk{C['sn']}")
    return 0


def komut_durum():
    durum = c.yukle(motor.DURUM)
    kaynak = kaynak_yukle()["mevzuat"]
    g = c.yukle(motor.GUNLUK, {"olaylar": []})
    eksik = [m["slug"] for m in kaynak if m["slug"] not in durum]
    ozet = {}
    for d in durum.values():
        for k, v in (d.get("madde_ozeti") or {}).items():
            ozet[k] = ozet.get(k, 0) + v
    surumler = {d.get("arac_surumu") for d in durum.values() if d.get("arac_surumu")}
    print(f"\n{C['kal']}SİSTEM DURUMU{C['sn']}")
    print(f"  izlenen mevzuat   : {len(kaynak)} ({len(durum)} indirilmiş, "
          f"{len(eksik)} eksik)")
    print(f"  toplam madde      : {sum(ozet.values())}")
    for k, v in sorted(ozet.items(), key=lambda x: -x[1]):
        print(f"      {analiz.DURUM_ADI.get(k, k):<26}{v}")
    print(f"  günlükteki olay   : {len(g['olaylar'])} "
          f"({sum(1 for o in g['olaylar'] if o.get('siddet') == 'kritik')} kritik, "
          f"{sum(1 for o in g['olaylar'] if not o.get('okundu'))} okunmamış)")
    print(f"  pdftotext         : {c.poppler_surumu()} "
          f"(kayıtlardaki: {', '.join(sorted(surumler)) or '—'})")
    u = c.tls_uyarisi()
    print(f"  TLS               : {C['kir'] + u + C['sn'] if u else C['yes'] + 'doğrulanıyor' + C['sn']}")
    if eksik:
        print(f"\n  {C['sar']}eksik: {', '.join(eksik[:8])}"
              f"{' …' if len(eksik) > 8 else ''}{C['sn']}")
    return 0


# ─────────────────────────────────────────────────── ara (numara çöz)
def komut_ara(ifade, tur="Yonetmelik"):
    import json
    import urllib.request
    govde = {"draw": 1, "columns": [], "order": [], "start": 0, "length": 20,
             "search": {"value": "", "regex": False},
             "parameters": {"AranacakIfade": ifade, "AranacakYer": "Baslik",
                            "MevzuatTur": tur, "TabloAdi": "MevzuatDataTable"}}
    istek = urllib.request.Request(
        "https://www.mevzuat.gov.tr/anasayfa/MevzuatDatatable",
        data=json.dumps(govde, ensure_ascii=False).encode(),
        headers={"User-Agent": c.UA, "Content-Type": "application/json",
                 "X-Requested-With": "XMLHttpRequest"}, method="POST")
    try:
        with urllib.request.urlopen(istek, timeout=40, context=c.baglam()) as y:
            veri = __import__("json").load(y).get("data", [])
    except Exception as e:
        print(f"{C['kir']}Arama başarısız: {e}{C['sn']}")
        return 2
    if not veri:
        print("Sonuç yok. Türü değiştir: Kanun · Yonetmelik · Teblig · "
              "CumhurbaskanligiKararnamesi")
        return 2
    for x in veri:
        ad = re.sub(r"<[^>]+>", "", x["mevAdi"]).replace("\r\n", " ").strip()
        print(f'  no={x["mevzuatNo"]:<10} tertip={x["mevzuatTertip"]}  '
              f'RG {x["resmiGazeteTarihi"]}/{x["resmiGazeteSayisi"]:<10} {ad[:66]}')
    print(f"\n{C['mav']}kaynak.json'a eklerken tur: Kanun → \"Kanun\" · "
          f"yönetmelik → \"KurumVeKurulusYonetmeligi\"{C['sn']}")
    return 0


def main():
    for d in (motor.PDF_DIR, motor.MET_DIR, motor.ARS_DIR):
        os.makedirs(d, exist_ok=True)
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help", "yardim"):
        print(__doc__)
        return 0
    k = a[0]
    bayrak = [x for x in a[1:] if x.startswith("--")]
    arg = [x for x in a[1:] if not x.startswith("-")]
    kuru = "--kuru" in bayrak
    atla = "--devre-kesiciyi-atla" in bayrak

    if k == "denetle":
        # denetle [slug...] — slug verilirse yalnız onlar (acil_is.py çekirdek
        # belgeleri gün içinde böyle denetler); verilmezse 51 kaydın hepsi.
        return _kos(arg, kuru, "GÜNCELLİK DENETİMİ", atla)
    if k == "indir":
        return _kos(arg, kuru, "İNDİRME", atla)
    if k == "liste":
        s = a[a.index("--sinif") + 1] if "--sinif" in a else None
        gr = a[a.index("--grup") + 1] if "--grup" in a else None
        return komut_liste(s, gr)
    if k == "madde":
        return komut_madde(arg[0], " ".join(arg[1:])) if len(arg) >= 2 else \
            (print("madde <slug> <no>   ör: madde 4857-is-kanunu 17") or 2)
    if k == "fark":
        return komut_fark(arg[0], "--kelime" in bayrak) if arg else \
            (print("fark <slug> [--kelime]") or 2)
    if k == "bul":
        return komut_bul(" ".join(arg)) if arg else (print('bul "<ifade>"') or 2)
    if k == "olaylar":
        n = int(a[a.index("-n") + 1]) if "-n" in a else 30
        return komut_olaylar("--kritik" in bayrak, n, arg[0] if arg else None)
    if k == "degisiklikler":
        import degisiklik
        return degisiklik.komut_liste(kuru, son="--son" in bayrak)
    if k == "degisiklik":
        import degisiklik
        return degisiklik.komut_detay(int(arg[0]), "--tam" in bayrak) \
            if arg and arg[0].isdigit() else (print("degisiklik <no> [--tam]   ör: degisiklik 5") or 2)
    if k == "durum":
        return komut_durum()
    if k == "ara":
        return komut_ara(arg[0], arg[1] if len(arg) > 1 else "Yonetmelik") if arg \
            else (print('ara "<ifade>" [Kanun|Yonetmelik|Teblig]') or 2)
    if k == "rg":
        import rg as rgm
        n = int(arg[0]) if arg and arg[0].isdigit() else 7
        return subprocess.call([sys.executable,
                                os.path.join(motor.KOK, "rg.py"), str(n)])
    if k == "etki":
        import etki
        return etki.komut(arg[0], arg[1] if len(arg) > 1 else None)
    print(f"Bilinmeyen komut: {k}")
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
