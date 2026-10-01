#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sunucu.py — mevzuat takip arayüzü · http://127.0.0.1:3031

PORT 3031 bu projeye SABİTLENMİŞTİR (PORTS_REGISTRY.md'ye işlendi).
Yalnız 127.0.0.1'e bağlanır — dışarı açık değildir.

Python stdlib; npm bağımlılığı yok. Ekosistemde emsali var:
dr.kim (3028), duru (3026), NAS-Sync (8081).
"""
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import analiz
import cekirdek as c
import motor

PORT = 3031
ADRES = "127.0.0.1"
ARAYUZ = os.path.join(motor.KOK, "arayuz")

# Denetim arka planda koşar; arayüz ilerlemeyi buradan okur.
_is = {"kosuyor": False, "baslangic": None, "bitis": None,
       "cikti": "", "kod": None, "tur": ""}
_kilit = threading.Lock()


def _denetim_kos(tur="denetle"):
    with _kilit:
        if _is["kosuyor"]:
            return False
        _is.update(kosuyor=True, baslangic=datetime.now().isoformat(timespec="seconds"),
                   bitis=None, cikti="", kod=None, tur=tur)

    def calis():
        try:
            komut = [sys.executable, os.path.join(motor.KOK, "mevzuat.py"), tur]
            r = subprocess.run(komut, capture_output=True, text=True, timeout=1800,
                               cwd=motor.KOK)
            ham = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout + r.stderr)
            with _kilit:
                _is.update(cikti=ham[-20000:], kod=r.returncode)
        except Exception as e:
            with _kilit:
                _is.update(cikti=f"{type(e).__name__}: {e}", kod=-1)
        finally:
            with _kilit:
                _is.update(kosuyor=False,
                           bitis=datetime.now().isoformat(timespec="seconds"))
    threading.Thread(target=calis, daemon=True).start()
    return True


class Vekil(BaseHTTPRequestHandler):
    server_version = "mevzuat/1.0"

    def log_message(self, bicim, *arg):
        pass                      # erişim günlüğü gürültü yapmasın

    # ── yardımcılar ──
    def _json(self, veri, kod=200):
        govde = json.dumps(veri, ensure_ascii=False).encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(govde)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(govde)

    def _dosya(self, yol):
        if not os.path.isfile(yol):
            return self._json({"hata": "bulunamadı"}, 404)
        tur = mimetypes.guess_type(yol)[0] or "application/octet-stream"
        if tur.startswith("text/") or tur == "application/javascript":
            tur += "; charset=utf-8"
        with open(yol, "rb") as f:
            govde = f.read()
        self.send_response(200)
        self.send_header("Content-Type", tur)
        self.send_header("Content-Length", str(len(govde)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(govde)

    # ── yönlendirme ──
    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        yol = p.path
        q = urllib.parse.parse_qs(p.query)

        if yol in ("/", "/gunluk", "/belge", "/ara", "/rg"):
            return self._dosya(os.path.join(ARAYUZ, "index.html"))
        if yol.startswith("/arayuz/"):
            ad = os.path.basename(yol)
            return self._dosya(os.path.join(ARAYUZ, ad))

        if yol == "/api/liste":
            return self._json(self._liste())
        if yol == "/api/ozet":
            return self._json(self._ozet())
        if yol.startswith("/api/belge/"):
            return self._json(self._belge(yol.split("/api/belge/", 1)[1]))
        if yol == "/api/gunluk":
            return self._json(self._gunluk(q))
        if yol == "/api/fark":
            return self._json(self._fark(q.get("slug", [""])[0],
                                         q.get("dosya", [""])[0]))
        if yol == "/api/madde":
            return self._json(self._madde(q.get("slug", [""])[0],
                                          q.get("no", [""])[0]))
        if yol == "/api/bul":
            return self._json(self._bul(q.get("q", [""])[0]))
        if yol == "/api/rg":
            return self._json(self._rg(int(q.get("gun", ["7"])[0])))
        if yol == "/api/denetim":
            with _kilit:
                return self._json(dict(_is))
        return self._json({"hata": "bilinmeyen uç"}, 404)

    def do_POST(self):
        p = urllib.parse.urlparse(self.path)
        yol = p.path
        # Yerel sunucuya başka bir siteden istek (CSRF) gelmesin: tarayıcı
        # POST'ta Origin gönderir; yalnız bu arayüzün kendi kökü kabul edilir.
        # Origin'siz istek (curl) tarayıcıdan gelmediği için geçer.
        koken = self.headers.get("Origin")
        if koken and koken not in (f"http://{ADRES}:{PORT}", f"http://localhost:{PORT}"):
            return self._json({"hata": "izin verilmeyen köken"}, 403)
        uzunluk = int(self.headers.get("Content-Length") or 0)
        govde = json.loads(self.rfile.read(uzunluk) or "{}") if uzunluk else {}

        if yol == "/api/denetle":
            tur = govde.get("tur", "denetle")
            if tur not in ("denetle", "rg"):
                return self._json({"hata": "geçersiz tür"}, 400)
            basladi = _denetim_kos(tur)
            return self._json({"basladi": basladi, **dict(_is)})
        if yol == "/api/acil":
            import acil_is
            try:
                kume = acil_is.acil_secim_degistir(str(govde.get("slug", "")),
                                                   bool(govde.get("acil")))
            except ValueError as e:
                return self._json({"hata": str(e)}, 400)
            return self._json({"tamam": True, "sayi": len(kume), "sluglar": sorted(kume)})
        if yol == "/api/olay/okundu":
            return self._json(self._okundu(govde.get("id"), govde.get("okundu", True),
                                           govde.get("not")))
        return self._json({"hata": "bilinmeyen uç"}, 404)

    # ── veri ──
    def _liste(self):
        import acil_is
        kaynak = c.kaynak()
        acil = acil_is.acil_sluglar(kaynak)
        durum = c.yukle(motor.DURUM)
        g = c.yukle(motor.GUNLUK, {"olaylar": []})
        son_olay = {}
        for o in g["olaylar"]:
            son_olay.setdefault(o.get("slug"), []).append(o)
        cikti = []
        for m in kaynak["mevzuat"]:
            d = durum.get(m["slug"], {})
            ol = son_olay.get(m["slug"], [])
            cikti.append({
                "slug": m["slug"], "ad": m["ad"], "no": m["no"], "tur": m["tur"],
                "sinif": m["sinif"], "grup": m.get("grup", []),
                "neden": m.get("neden", ""),
                "kritik_madde": m.get("kritik_madde", []),
                "indirildi": bool(d),
                "madde": d.get("madde"), "sayfa": d.get("sayfa"),
                "madde_ozeti": d.get("madde_ozeti", {}),
                "son_dogrulama": d.get("son_dogrulama"),
                "son_degisiklik": d.get("son_degisiklik"),
                "imza": (d.get("imza") or "")[:12],
                "imza_turu": d.get("imza_turu"),
                "sayfa_url": d.get("sayfa_url"), "url": d.get("url"),
                "mukerrer": d.get("mukerrer", []),
                "olay_sayisi": len(ol),
                "okunmamis": sum(1 for o in ol if not o.get("okundu")),
                "acil": m["slug"] in acil,
            })
        return {"mevzuat": cikti, "sinif": kaynak.get("_sinif", {})}

    def _ozet(self):
        durum = c.yukle(motor.DURUM)
        kaynak = c.kaynak()
        g = c.yukle(motor.GUNLUK, {"olaylar": []})
        madde = {}
        for d in durum.values():
            for k, v in (d.get("madde_ozeti") or {}).items():
                madde[k] = madde.get(k, 0) + v
        sondog = [d.get("son_dogrulama") for d in durum.values() if d.get("son_dogrulama")]
        return {
            "izlenen": len(kaynak["mevzuat"]), "indirilen": len(durum),
            "madde": madde, "toplam_madde": sum(madde.values()),
            "olay": len(g["olaylar"]),
            "kritik": sum(1 for o in g["olaylar"] if o.get("siddet") == "kritik"),
            "okunmamis": sum(1 for o in g["olaylar"] if not o.get("okundu")),
            "son_dogrulama": max(sondog) if sondog else None,
            "poppler": c.poppler_surumu(),
            "tls": c.tls_uyarisi() or "doğrulanıyor",
            "port": PORT,
        }

    def _belge(self, slug):
        slug = urllib.parse.unquote(slug)
        kaynak = c.kaynak()
        m = next((x for x in kaynak["mevzuat"] if x["slug"] == slug), None)
        if not m:
            return {"hata": "bilinmeyen kayıt"}
        d = c.yukle(motor.DURUM).get(slug, {})
        g = c.yukle(motor.GUNLUK, {"olaylar": []})
        env = d.get("envanter") or {}
        kritik = {str(x) for x in m.get("kritik_madde", [])}
        maddeler = [{
            "no": k, "durum": v["durum"], "durum_adi": analiz.DURUM_ADI[v["durum"]],
            "satir": v["satir"], "uzunluk": v["uzunluk"], "sha": v["sha"],
            "kunye": v.get("kunye", ""), "dipnot": v.get("dipnot", []),
            "dipnot_blok": v.get("dipnot_blok", []),
            "kritik": k in kritik,
        } for k, v in sorted(env.items(), key=lambda x: analiz._sirala(x[0]))]
        farklar = sorted(
            f for f in os.listdir(motor.ARS_DIR)
            if f.startswith(slug + "_") and f.endswith("_fark.diff"))
        return {
            "kaynak": m, "durum": {k: v for k, v in d.items() if k != "envanter"},
            "maddeler": maddeler,
            "olaylar": [o for o in g["olaylar"] if o.get("slug") == slug][::-1],
            "farklar": farklar[::-1],
        }

    def _gunluk(self, q):
        g = c.yukle(motor.GUNLUK, {"olaylar": []})
        ol = g["olaylar"][::-1]
        siddet = q.get("siddet", [""])[0]
        slug = q.get("slug", [""])[0]
        if siddet:
            ol = [o for o in ol if o.get("siddet") == siddet]
        if slug:
            ol = [o for o in ol if o.get("slug") == slug]
        if q.get("okunmamis", [""])[0] == "1":
            ol = [o for o in ol if not o.get("okundu")]
        return {"olaylar": ol[:int(q.get("n", ["300"])[0])], "toplam": len(g["olaylar"])}

    def _fark(self, slug, dosya):
        if not re.fullmatch(r"[A-Za-z0-9._-]+", dosya or ""):
            return {"hata": "geçersiz dosya adı"}
        yol = os.path.join(motor.ARS_DIR, dosya)
        if not os.path.isfile(yol) or not dosya.startswith(slug + "_"):
            return {"hata": "fark dosyası yok"}
        with open(yol, encoding="utf-8") as f:
            ham = f.read()
        return {"dosya": dosya, "diff": ham[:400000],
                "kelime": self._kelime_bloklari(ham)}

    @staticmethod
    def _kelime_bloklari(ham):
        """Ö-3: diff bloklarını kelime düzeyinde yeniden çıkarır."""
        import difflib
        bloklar, eski, yeni, cikti = [], [], [], []

        def dok():
            if eski or yeni:
                bloklar.append(("\n".join(eski).strip(), "\n".join(yeni).strip()))
            eski.clear()
            yeni.clear()
        for s in ham.splitlines():
            if s.startswith(("+++", "---")):
                continue
            if s.startswith("@@"):
                dok()
            elif s.startswith("-"):
                eski.append(s[1:])
            elif s.startswith("+"):
                yeni.append(s[1:])
            else:
                dok()
        dok()
        for a, b in bloklar[:200]:
            if not a and not b:
                continue
            ap, bp = a.split(), b.split()
            sm = difflib.SequenceMatcher(None, ap, bp, autojunk=False)
            parca = []
            for etiket, i1, i2, j1, j2 in sm.get_opcodes():
                if etiket == "equal":
                    parca.append({"t": "e", "m": " ".join(ap[i1:i2])})
                else:
                    if i1 != i2:
                        parca.append({"t": "-", "m": " ".join(ap[i1:i2])})
                    if j1 != j2:
                        parca.append({"t": "+", "m": " ".join(bp[j1:j2])})
            cikti.append(parca)
        return cikti

    def _madde(self, slug, no):
        yol = os.path.join(motor.MET_DIR, slug + ".txt")
        if not os.path.isfile(yol) or not re.fullmatch(r"[a-z0-9-]+", slug):
            return {"hata": "belge yok"}
        with open(yol, encoding="utf-8") as f:
            metin = f.read()
        d = c.yukle(motor.DURUM).get(slug, {})
        bilgi = (d.get("envanter") or {}).get(no)
        if not bilgi:
            return {"hata": f"madde {no} yok"}
        son = analiz.govde_siniri(metin)
        govde = metin[:son]
        isaret = list(analiz.MADDE.finditer(govde))
        for i, m in enumerate(isaret):
            if govde.count("\n", 0, m.start()) + 1 == bilgi["satir"]:
                bit = isaret[i + 1].start() if i + 1 < len(isaret) else son
                return {"slug": slug, "no": no, "durum": bilgi["durum"],
                        "durum_adi": analiz.DURUM_ADI[bilgi["durum"]],
                        "kunye": bilgi.get("kunye", ""),
                        "dipnot_blok": bilgi.get("dipnot_blok", []),
                        "metin": re.sub(r"\n{3,}", "\n\n", govde[m.start():bit]).rstrip(),
                        "ad": d.get("ad"), "url": d.get("url"),
                        "sayfa_url": d.get("sayfa_url"),
                        "son_dogrulama": d.get("son_dogrulama")}
        return {"hata": "envanter metinle uyuşmuyor — denetle çalıştır"}

    def _bul(self, ifade):
        if not ifade or len(ifade) < 2:
            return {"sonuc": [], "hata": "en az 2 karakter"}
        try:
            desen = re.compile(ifade, re.IGNORECASE)
        except re.error:
            desen = re.compile(re.escape(ifade), re.IGNORECASE)
        durum = c.yukle(motor.DURUM)
        sonuc = []
        for ad in sorted(os.listdir(motor.MET_DIR)):
            if not ad.endswith(".txt"):
                continue
            slug = ad[:-4]
            with open(os.path.join(motor.MET_DIR, ad), encoding="utf-8") as f:
                metin = f.read()
            eslesme = list(desen.finditer(metin))
            if not eslesme:
                continue
            d = durum.get(slug, {})
            env = d.get("envanter") or {}
            sinirlar = sorted((v["satir"], k) for k, v in env.items())
            gecis = []
            for m in eslesme[:6]:
                satir = metin.count("\n", 0, m.start()) + 1
                madde = ""
                for sn, k in sinirlar:
                    if sn <= satir:
                        madde = k
                    else:
                        break
                bas = max(0, m.start() - 90)
                gecis.append({"madde": madde, "satir": satir,
                              "baglam": re.sub(r"\s+", " ",
                                               metin[bas:m.end() + 90]).strip(),
                              "eslesme": m.group(0)})
            sonuc.append({"slug": slug, "ad": d.get("ad", slug),
                          "sinif": d.get("sinif", ""),
                          "toplam": len(eslesme), "gecis": gecis})
        sonuc.sort(key=lambda x: -x["toplam"])
        return {"sonuc": sonuc, "ifade": ifade}

    def _rg(self, gun):
        import rg as rgm
        kaynak = c.kaynak()
        b, h, t = rgm.tara(max(1, min(gun, 60)), izlenen=kaynak.get("mevzuat", []))
        return {"bulgular": b[::-1], "hatalar": h, "gun": t}

    def _okundu(self, olay_id, okundu, not_metni):
        g = c.yukle(motor.GUNLUK, {"olaylar": []})
        for o in g["olaylar"]:
            if o.get("id") == olay_id:
                o["okundu"] = bool(okundu)
                if not_metni is not None:
                    o["not"] = str(not_metni)[:2000]
                c.kaydet(motor.GUNLUK, g)
                return {"tamam": True, "olay": o}
        return {"hata": "olay bulunamadı"}


def main():
    os.makedirs(ARAYUZ, exist_ok=True)
    sunucu = ThreadingHTTPServer((ADRES, PORT), Vekil)
    u = c.tls_uyarisi()
    print(f"mevzuat arayüzü → http://{ADRES}:{PORT}")
    print(f"  izlenen: {len(c.kaynak().get('mevzuat', []))} mevzuat · "
          f"pdftotext {c.poppler_surumu()} · TLS: {u or 'doğrulanıyor'}")
    try:
        sunucu.serve_forever()
    except KeyboardInterrupt:
        print("\nkapatılıyor…")
        sunucu.shutdown()


if __name__ == "__main__":
    main()
