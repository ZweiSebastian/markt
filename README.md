# Markt

Android-App: täglicher **Shiller-KGV (CAPE)** des S&P 500 mit Ø und ±1σ/±2σ über 5/10/20 Jahre,
dazu **S&P-500-Wochenkerzen** der letzten 5 Jahre mit 200- und 50-Tage-Linie.

- `scripts/update.py` – berechnet die Daten (Shiller ie_data.xls + Yahoo-Tageskurse) → `data/markt.json`
- `.github/workflows/update-data.yml` – läuft jeden Handelstag nach US-Börsenschluss
- `.github/workflows/build.yml` – baut die APK (Releases)
