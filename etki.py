#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
etki.py — "Bu madde değişti, hangi belgemi etkiler?" (Ö-2)

NEDEN VAR: is-hukuku/mevzuat/OKU.md bu adımı bugün ELLE yaptırıyor —
"o maddeye atıf yapan her belgeyi bul: grep -rn 'm\\.17' ...".
Ölçüm (19.09.2026): yalnız is-hukuku'da 2.497 madde atıfı / 83 dosya var.
Elle grep hem unutulur hem eksik kalır.

Salt okunurdur: hiçbir dosyayı değiştirmez.
"""
import os
import re
import sys

import cekirdek as c

# Taranacak kökler kaynak.json'daki `_atif_kokleri` alanından gelir.
ATLA_DIZIN = {".git", "node_modules", ".venv", "__pycache__", ".next",
              "pdf", "arsiv", "metin", "pdf-md", ".vercel", "dist", "build",
              "_yedek", "_silinecek", "arşiv"}
TARA_UZANTI = {".md", ".py", ".js", ".mjs", ".ts", ".tsx", ".jsx",
               ".html", ".json", ".txt", ".yml", ".yaml"}


def desenler(no, madde):
    """Bir maddeye yapılabilecek atıf biçimleri.

    Türkçe hukuk yazımında aynı maddeye çok farklı yazılır:
        m.17 · md.17 · madde 17 · 17. madde · 17 nci madde · 4857/17
    Ek/Geçici maddeler ayrı ele alınır.
    """
    madde = str(madde).strip()
    ek = ""
    g = re.match(r"^(Ek|Geçici|Mükerrer)\s+(.+)$", madde, re.IGNORECASE)
    if g:
        ek, madde = g.group(1), g.group(2)
    n = re.escape(madde)
    if ek:
        on = {"ek": r"[Ee]k", "geçici": r"[Gg]eçici", "mükerrer": r"[Mm]ükerrer"}[
            ek.lower().replace("i̇", "i")]
        return [rf"{on}\s*(?:[Mm]adde|m\.|md\.)\s*{n}\b",
                rf"{on}\s*m\.?\s*{n}\b"]
    return [
        rf"\bm\.\s?{n}\b",
        rf"\bmd\.\s?{n}\b",
        rf"\b[Mm]adde\s*{n}\b",
        rf"\bMADDE\s*{n}\b",
        rf"\b{n}\s*(?:inci|nci|ıncı|uncu|üncü|\.)\s*madde",
        rf"\b{no}\s*/\s*{n}\b",
    ]


def tara(kokler, no, madde, sinir=200):
    """-> [(dosya, satir_no, satir)]"""
    d = [re.compile(x) for x in desenler(no, madde)]
    bulgu = []
    for kok in kokler:
        kok = os.path.expanduser(kok)
        if not os.path.isdir(kok):
            continue
        for dizin, altlar, dosyalar in os.walk(kok):
            altlar[:] = [a for a in altlar
                         if a not in ATLA_DIZIN and not a.startswith(".")]
            for ad in dosyalar:
                if os.path.splitext(ad)[1].lower() not in TARA_UZANTI:
                    continue
                yol = os.path.join(dizin, ad)
                try:
                    if os.path.getsize(yol) > 2_000_000:
                        continue
                    with open(yol, encoding="utf-8", errors="ignore") as f:
                        for i, satir in enumerate(f, 1):
                            if any(x.search(satir) for x in d):
                                bulgu.append((yol, i, satir.strip()[:160]))
                                if len(bulgu) >= sinir:
                                    return bulgu
                except OSError:
                    continue
    return bulgu


def komut(slug, madde):
    if not madde:
        print("etki <slug> <madde>   ör: etki 4857-is-kanunu 17")
        return 2
    kaynak = c.kaynak()
    m = next((x for x in kaynak["mevzuat"] if x["slug"] == slug), None)
    if not m:
        print(f"Bilinmeyen kayıt: {slug}")
        return 2
    kokler = kaynak.get("_atif_kokleri") or []
    if not kokler:
        print("Taranacak proje kökü tanımlı değil.\n"
              "`kaynak-notlar.json` (git dışı) içine `_atif_kokleri` ekle:\n"
              '  {"_atif_kokleri": ["~/Projects/<proje>"]}')
        return 2

    bulgu = tara(kokler, m["no"], madde)
    kritik = str(madde) in {str(x) for x in m.get("kritik_madde", [])}
    print(f"\n{m['ad']} — madde {madde}"
          + ("  [KRİTİK MADDE]" if kritik else ""))
    print(f"taranan kök: {', '.join(kokler)}")
    print("─" * 82)
    if not bulgu:
        print("Bu maddeye atıf yapan dosya bulunamadı.")
        print("(Atıf başka biçimde yazılmış olabilir — `bul` ile metinde ara.)")
        return 0
    gruplu = {}
    for yol, i, satir in bulgu:
        gruplu.setdefault(yol, []).append((i, satir))
    for yol, satirlar in sorted(gruplu.items()):
        kisa = yol
        for k in kokler:
            k = os.path.expanduser(k)
            if yol.startswith(k):
                kisa = os.path.relpath(yol, os.path.dirname(k))
                break
        print(f"\n{kisa}  ({len(satirlar)} atıf)")
        for i, satir in satirlar[:3]:
            print(f"   {i:>5}: {satir}")
        if len(satirlar) > 3:
            print(f"         … {len(satirlar)-3} atıf daha")
    print("\n" + "─" * 82)
    print(f"{len(gruplu)} dosyada {len(bulgu)} atıf. "
          + ("Bu madde KRİTİK işaretli — değişikliği mutlaka incelenmeli."
             if kritik else ""))
    print("⚠ 'm.17' gibi çıplak atıflar HANGİ kanunun maddesi olduğunu söylemez; "
          "liste fazla kapsayıcıdır (ör. HMK m.17 de eşleşir). Gözle doğrula.")
    return 0


if __name__ == "__main__":
    sys.exit(komut(sys.argv[1] if len(sys.argv) > 1 else "",
                   sys.argv[2] if len(sys.argv) > 2 else None))
