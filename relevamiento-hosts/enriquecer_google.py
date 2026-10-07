"""Completa teléfono comercial, web y ficha de Google Maps de alojamientos de Booking
y de las inmobiliarias, usando la API oficial de Google Places.

Solo busca negocios (alojamientos de Booking e inmobiliarias). No se usa para buscar
datos personales de anfitriones particulares de Airbnb.

Necesita una clave de Google Maps Platform con "Places API (New)" habilitada:
    export GOOGLE_PLACES_KEY="tu-clave"      (Mac/Linux)
    python3 enriquecer_google.py

Google da un crédito mensual gratis; cada búsqueda cuesta unos centavos de dólar.
"""
import json
import os
import sys
import time
import urllib.request

from comun import cargar_progreso, guardar_progreso

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
CAMPOS = ",".join([
    "places.displayName", "places.formattedAddress", "places.nationalPhoneNumber",
    "places.internationalPhoneNumber", "places.websiteUri", "places.googleMapsUri",
    "places.businessStatus", "places.rating", "places.userRatingCount", "places.location",
])


def buscar(clave, texto, lat=None, lng=None):
    cuerpo = {"textQuery": texto, "languageCode": "es", "regionCode": "UY", "maxResultCount": 1}
    if lat is not None and lng is not None:
        cuerpo["locationBias"] = {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": 500.0}}
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(cuerpo).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Goog-Api-Key": clave, "X-Goog-FieldMask": CAMPOS},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        datos = json.load(r)
    lugares = datos.get("places") or []
    if not lugares:
        return {"google_encontrado": False}
    p = lugares[0]
    return {
        "google_encontrado": True,
        "google_nombre": (p.get("displayName") or {}).get("text", ""),
        "google_direccion": p.get("formattedAddress", ""),
        "telefono": p.get("nationalPhoneNumber") or p.get("internationalPhoneNumber", ""),
        "web": p.get("websiteUri", ""),
        "google_maps_url": p.get("googleMapsUri", ""),
        "google_estado": p.get("businessStatus", ""),
        "google_puntaje": p.get("rating", ""),
        "google_resenas": p.get("userRatingCount", ""),
    }


def main():
    clave = os.environ.get("GOOGLE_PLACES_KEY")
    if not clave:
        sys.exit("Falta la clave: export GOOGLE_PLACES_KEY=\"...\" (ver instrucciones en el README).")
    prog = cargar_progreso("booking")
    alojamientos = prog.get("alojamientos", {})
    pendientes = [a for a in alojamientos.values() if "google_encontrado" not in a and not a.get("fuera_de_zona")]
    print(f"Buscando en Google {len(pendientes)} alojamientos de Booking...")
    for i, a in enumerate(pendientes, 1):
        texto = f"{a.get('nombre_pagina') or a['nombre']}, {a.get('direccion') or a.get('direccion_tarjeta', '')}, Uruguay"
        try:
            a.update(buscar(clave, texto, a.get("lat"), a.get("lng")))
        except Exception as ex:  # noqa: BLE001
            print(f"  error con {a['nombre']}: {ex}")
            if "403" in str(ex) or "400" in str(ex):
                sys.exit("La clave fue rechazada: revisá que tenga habilitada 'Places API (New)'.")
        if i % 20 == 0:
            guardar_progreso("booking", prog)
            print(f"  {i}/{len(pendientes)}")
        time.sleep(0.2)
    guardar_progreso("booking", prog)
    print("Listo. Ahora corré: python3 exportar_excel.py")


if __name__ == "__main__":
    main()
