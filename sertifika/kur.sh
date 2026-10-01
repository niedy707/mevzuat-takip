#!/usr/bin/env bash
# kur.sh — mevzuat.gov.tr icin CA bundle'i uretir; "curl -k"yi gereksiz kilar.
#
# NEDEN: www.mevzuat.gov.tr zincirde YALNIZ leaf sertifikayi gonderiyor
# (CN=*.tccb.gov.tr, "Verify return code: 21"). Tarayici eksik ara sertifikayi
# AIA uzantisindan kendi ceker; curl'de AIA destegi RESMEN YOKTUR (curl TODO
# listesinde, issue #2793 oraya devredildi). Bu bir MITM isareti degil, sunucu
# yapilandirma eksikligidir -- ama "-k" ile dogrulamayi tamamen kapatmak, isi
# resmi metnin dogrulugunu garanti etmek olan bir arac icin kabul edilemez.
# curl'un kendi belgesi: "we strongly recommend this is avoided ... never skip
# verification in production."
#
# COZUM: ara sertifikayi AIA adresinden BIR KEZ indir, koke ekle, --cacert ver.
#
# TUZAK (19.09.2026'da yasandi): ara sertifikanin imzalayani
# "DigiCert Global Root G2"dir -- "DigiCert Global Root CA" DEGILDIR.
# Yanlis kokle openssl verify sessizce basarisiz olur.
set -euo pipefail
KOK="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$KOK/mevzuat-ca.pem"
ARA_URL="http://cacerts.geotrust.com/GeoTrustTLSRSACAG1.crt"
KOK_ADI="DigiCert Global Root G2"

echo "1) Ara sertifika indiriliyor (duz HTTP -- TLS engeli yok)..."
curl -fsS -o "$KOK/ara.der" "$ARA_URL"
openssl x509 -inform DER -in "$KOK/ara.der" -out "$KOK/ara.pem"
rm -f "$KOK/ara.der"

echo "2) Kok sertifika sistem deposundan aliniyor: $KOK_ADI"
security find-certificate -c "$KOK_ADI" -p \
  /System/Library/Keychains/SystemRootCertificates.keychain > "$KOK/kok.pem"
grep -q "BEGIN CERTIFICATE" "$KOK/kok.pem" || { echo "HATA: kok sertifika bulunamadi"; exit 1; }

cat "$KOK/ara.pem" "$KOK/kok.pem" > "$BUNDLE"
rm -f "$KOK/ara.pem" "$KOK/kok.pem"

echo "3) Dogrulama: -k YOK, --cacert VAR"
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
if curl -sS -A "$UA" --cacert "$BUNDLE" -o /dev/null \
     -w '   HTTP %{http_code}\n' --max-time 45 \
     "https://www.mevzuat.gov.tr/MevzuatMetin/1.5.634.pdf"; then
  echo "   ✅ bundle calisiyor: $BUNDLE"
  openssl x509 -in "$BUNDLE" -noout -enddate | sed 's/^/   ara sertifika /'
  echo "   ⚠️  Bu tarihten once kur.sh yeniden calistirilmali."
else
  echo "   ❌ dogrulama basarisiz -- motor -k'ye geri duser (mevzuat.py uyarir)"; exit 1
fi
