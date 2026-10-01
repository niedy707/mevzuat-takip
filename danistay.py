#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
danistay.py — Danıştay karar aramasında yürütme durdurma taraması (Ö-7)

⚠️ BU BİR ERKEN UYARI KANALI DEĞİLDİR — elle araştırma aracıdır.

Neden: Danıştay karar bankasına kararlar SEÇİLEREK ve GECİKMEYLE yüklenir;
sonuç listesinde yayın tarihi alanı yoktur ve bir yönetmeliğe açılan davadaki
yürütme durdurma kararının burada hiç yayımlanmama ihtimali vardır.
ÖLÇÜM (19.09.2026): "yürütmenin durdurulması" + "özel hastaneler" sorgusu
20.884 kayıt döndürdü — `andKelimeler` dar bir kesişim üretmiyor.

Gerçek erken sinyal Resmî Gazete'dir (`rg.py`). Bu modül, bir yönetmelikte
zaten bir değişiklik/şerh görüldükten SONRA "arkasındaki karar neydi" diye
bakmak için vardır.

    python3 danistay.py "özel hastaneler" [ek kelime...]
"""
import json
import sys
import urllib.request

import cekirdek as c

UC = "https://karararama.danistay.gov.tr/aramalist"
BELGE = "https://karararama.danistay.gov.tr/getDokuman?id={}"


def ara(kelimeler, sayfa_boyu=20, sayfa=1):
    """-> (toplam, [kayit]) · hata durumunda (None, [])"""
    govde = {"data": {"andKelimeler": list(kelimeler), "orKelimeler": [],
                      "notAndKelimeler": [], "notOrKelimeler": [],
                      "pageSize": sayfa_boyu, "pageNumber": sayfa}}
    istek = urllib.request.Request(
        UC, data=json.dumps(govde, ensure_ascii=False).encode(),
        headers={"User-Agent": c.UA, "Content-Type": "application/json",
                 "X-Requested-With": "XMLHttpRequest",
                 "Origin": "https://karararama.danistay.gov.tr",
                 "Referer": "https://karararama.danistay.gov.tr/"},
        method="POST")
    try:
        with urllib.request.urlopen(istek, timeout=45) as y:
            d = json.load(y)
    except Exception as e:
        print(f"Danıştay araması başarısız: {type(e).__name__}: {e}", file=sys.stderr)
        return None, []
    veri = d.get("data") or {}
    return veri.get("recordsTotal"), (veri.get("data") or [])


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    kelimeler = ["yürütmenin durdurulması"] + sys.argv[1:]
    toplam, kayitlar = ara(kelimeler)
    if toplam is None:
        return 2
    print(f"\nDanıştay karar araması · {' + '.join(kelimeler)}")
    print(f"toplam eşleşme: {toplam}")
    print("─" * 78)
    for x in kayitlar:
        print(f"  {str(x.get('daireKurul') or '—'):<28} "
              f"E:{x.get('esasNo')} K:{x.get('kararNo')}  {x.get('kararTarihi')}")
        if x.get("id"):
            print(f"      {BELGE.format(x['id'])}")
    print("─" * 78)
    print("⚠️ Bu liste alaka sırasına göre değildir ve yayın gecikmesi ölçülemez.")
    print("   Erken uyarı için `python3 mevzuat.py rg` (Resmî Gazete) kullanılır.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
