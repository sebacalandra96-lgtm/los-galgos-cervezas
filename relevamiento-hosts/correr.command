#!/bin/bash
# Doble clic en este archivo (Mac) para instalar lo necesario y correr todo el relevamiento.
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null; then
  echo "Falta Python 3. Instalalo desde https://www.python.org/downloads/ y volvé a abrir este archivo."
  read -r -p "Enter para cerrar"; exit 1
fi

if [ ! -d .venv ]; then
  echo "Instalando dependencias (solo la primera vez)..."
  python3 -m venv .venv || exit 1
  ./.venv/bin/pip install -q -r requirements.txt || exit 1
  ./.venv/bin/python -m playwright install chromium || exit 1
fi

PY=./.venv/bin/python
echo; echo "== 1/4 Booking =="; $PY scrape_booking.py
echo; echo "== 2/4 Airbnb ==";  $PY scrape_airbnb.py
if [ -n "$GOOGLE_PLACES_KEY" ] || [ -f clave_google.txt ]; then
  [ -z "$GOOGLE_PLACES_KEY" ] && export GOOGLE_PLACES_KEY="$(tr -d '[:space:]' < clave_google.txt)"
  echo; echo "== 3/4 Teléfonos comerciales (Google) =="; $PY enriquecer_google.py
else
  echo; echo "== 3/4 Google: salteado (no hay clave_google.txt) =="
fi
echo; echo "== 4/4 Excel =="; $PY exportar_excel.py
open base_hosts_uruguay.xlsx 2>/dev/null
read -r -p "Terminado. Enter para cerrar"
