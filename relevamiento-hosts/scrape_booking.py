"""Relevamiento de alojamientos de Booking en Montevideo, Maldonado y Rocha.

Busca localidad por localidad (Booking corta en ~1000 resultados por búsqueda),
elimina duplicados y después entra a cada alojamiento para leer dirección,
coordenadas y quién lo gestiona. Guarda el progreso en datos/booking.json.

Uso:
    python3 scrape_booking.py
    python3 scrape_booking.py --zona Rocha
    python3 scrape_booking.py --sin-detalle
"""
import argparse
import re
import sys
from urllib.parse import urlencode, urlsplit, urlunsplit

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

from comun import LOCALIDADES_BOOKING, cargar_progreso, departamento_por_coordenadas, guardar_progreso, pausa

BASE = "https://www.booking.com"

JS_TARJETAS = r"""
() => [...document.querySelectorAll('[data-testid="property-card"]')].map(c => {
  const t = (sel) => { const e = c.querySelector(sel); return e ? e.innerText.replace(/\s+/g, ' ').trim() : ''; };
  const a = c.querySelector('a[data-testid="title-link"]') || c.querySelector('a[href*="/hotel/"]');
  return {
    nombre: t('[data-testid="title"]'),
    url: a ? a.href : '',
    direccion_tarjeta: t('[data-testid="address"]'),
    puntaje: t('[data-testid="review-score"]'),
    distancia: t('[data-testid="distance"]'),
    texto: c.innerText.replace(/\s+/g, ' ').trim().slice(0, 600),
  };
})
"""

JS_DETALLE = r"""
() => {
  const r = {};
  const cuerpo = document.body.innerText;
  const ll = document.querySelector('[data-atlas-latlng]');
  if (ll) {
    const [lat, lng] = ll.getAttribute('data-atlas-latlng').split(',').map(parseFloat);
    r.lat = lat; r.lng = lng;
  }
  const dir = document.querySelector('[data-testid="PropertyHeaderAddressDesktop-wrapper"], .hp_address_subtitle, [data-node_tt_id="location_score_tooltip"]');
  if (dir) r.direccion = dir.innerText.split('\n')[0].trim();
  const h2 = document.querySelector('h2.pp-header__title, [data-testid="property-name"], h2');
  if (h2) r.nombre_pagina = h2.innerText.trim();
  const gest = cuerpo.match(/(?:Gestionado por|Administrado por|Managed by|Hosted by|Anfitri[oó]n)\s*:?\s*([^\n]+)/i);
  if (gest) r.gestionado_por = gest[1].trim();
  r.particular = /(?:gestionad[oa]|administrad[oa]) por un particular|managed by a private host|private host/i.test(cuerpo);
  r.profesional = /(?:gestionad[oa]|administrad[oa]) por (?:un|una) (?:anfitri[oó]n )?profesional|professional host/i.test(cuerpo);
  const tipo = document.querySelector('[data-testid="property-type-badge"], .bui-badge');
  if (tipo) r.tipo = tipo.innerText.trim();
  const estrellas = document.querySelectorAll('[data-testid="rating-stars"] span, [data-testid="rating-squares"] span').length;
  if (estrellas) r.estrellas = estrellas;
  const resenas = cuerpo.match(/(\d[\d.,]*)\s+(?:comentarios|reseñas|reviews)/i);
  if (resenas) r.resenas = parseInt(resenas[1].replace(/[.,]/g, ''));
  return r;
}
"""


def limpiar_url(url):
    """Saca los parámetros de seguimiento para que la URL sirva de identificador."""
    partes = urlsplit(url)
    return urlunsplit((partes.scheme, partes.netloc, partes.path, "", ""))


def url_busqueda(localidad, offset=0):
    q = {"ss": f"{localidad}, Uruguay", "lang": "es", "offset": offset, "group_adults": 2}
    return f"{BASE}/searchresults.es.html?{urlencode(q)}"


def parse_puntaje(texto):
    r = {}
    m = re.search(r"(\d{1,2}[.,]\d)", texto or "")
    if m:
        r["puntaje_num"] = float(m.group(1).replace(",", "."))
    m = re.search(r"(\d[\d.,]*)\s+(?:comentarios|reseñas|reviews)", texto or "", re.I)
    if m:
        r["resenas"] = int(re.sub(r"[.,]", "", m.group(1)))
    return r


def detectar_bloqueo(pagina):
    texto = pagina.inner_text("body")[:3000].lower()
    return any(p in texto for p in ("captcha", "verifica que eres humano", "are you a robot", "access denied"))


def cerrar_popups(pagina):
    for sel in ('#onetrust-accept-btn-handler', 'button[aria-label*="Ignorar"]', 'button[aria-label*="Dismiss"]',
                'button[aria-label*="Cerrar"]'):
        try:
            b = pagina.locator(sel)
            if b.count() and b.first.is_visible():
                b.first.click(timeout=1500)
        except Exception:
            pass


def buscar_localidad(pagina, depto, localidad, prog):
    clave = f"{depto}|{localidad}"
    if clave in prog["busquedas_hechas"]:
        return
    pagina.goto(url_busqueda(localidad), wait_until="domcontentloaded", timeout=60000)
    pausa()
    cerrar_popups(pagina)
    if detectar_bloqueo(pagina):
        print("\n⚠️  Booking pidió verificación. Resolvelo en la ventana del navegador y apretá Enter acá.")
        input()
    try:
        pagina.wait_for_selector('[data-testid="property-card"]', timeout=25000)
    except PWTimeout:
        print(f"  {localidad}: sin resultados")
        prog["busquedas_hechas"].append(clave)
        return

    # Booking muestra "Cargar más resultados" al final de la lista; se aprieta hasta que no aparezca más.
    anteriores = -1
    for _ in range(60):
        cantidad = pagina.locator('[data-testid="property-card"]').count()
        if cantidad == anteriores:
            break
        anteriores = cantidad
        pagina.mouse.wheel(0, 20000)
        pausa(1.5, 3.0)
        cerrar_popups(pagina)
        boton = pagina.locator('button:has-text("Cargar más resultados"), button:has-text("Load more results")')
        if boton.count() and boton.first.is_visible():
            boton.first.click()
            pausa(2.0, 4.0)

    nuevos = 0
    for t in pagina.evaluate(JS_TARJETAS):
        if not t["url"]:
            continue
        t["url"] = limpiar_url(t["url"])
        if t["url"] not in prog["alojamientos"]:
            nuevos += 1
            t.update(parse_puntaje(t["puntaje"]))
            t["zona_busqueda"] = depto
            t["localidad_busqueda"] = localidad
            prog["alojamientos"][t["url"]] = t
    print(f"  {localidad}: {anteriores} en pantalla, {nuevos} nuevos (acumulado {len(prog['alojamientos'])})")
    prog["busquedas_hechas"].append(clave)
    guardar_progreso("booking", prog)


def leer_detalles(pagina, prog):
    pendientes = [a for a in prog["alojamientos"].values() if not a.get("detalle_ok")]
    print(f"\nLeyendo detalle de {len(pendientes)} alojamientos...")
    for i, a in enumerate(pendientes, 1):
        try:
            pagina.goto(a["url"] + "?lang=es", wait_until="domcontentloaded", timeout=60000)
            pausa(1.5, 3.5)
            cerrar_popups(pagina)
            if detectar_bloqueo(pagina):
                print("\n⚠️  Booking pidió verificación. Resolvelo en el navegador y apretá Enter acá.")
                input()
            pagina.mouse.wheel(0, 8000)
            pausa(1.0, 2.0)
            det = pagina.evaluate(JS_DETALLE)
            for k, v in det.items():
                if v not in (None, ""):
                    a[k] = v
            depto = departamento_por_coordenadas(a.get("lat"), a.get("lng"))
            a["departamento"] = depto or a["zona_busqueda"]
            # Las búsquedas por localidad a veces traen alojamientos de departamentos vecinos.
            a["fuera_de_zona"] = bool(a.get("lat")) and not depto
            a["detalle_ok"] = True
        except PWTimeout:
            a["error"] = "timeout"
        except Exception as ex:  # noqa: BLE001
            a["error"] = str(ex)[:200]
        if i % 10 == 0:
            guardar_progreso("booking", prog)
            print(f"  {i}/{len(pendientes)}")
    guardar_progreso("booking", prog)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zona", choices=list(LOCALIDADES_BOOKING), action="append")
    ap.add_argument("--sin-detalle", action="store_true")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()

    prog = cargar_progreso("booking") or {}
    prog.setdefault("alojamientos", {})
    prog.setdefault("busquedas_hechas", [])

    with sync_playwright() as pw:
        nav = pw.chromium.launch(headless=args.headless)
        ctx = nav.new_context(locale="es-UY", timezone_id="America/Montevideo",
                              viewport={"width": 1400, "height": 900})
        pagina = ctx.new_page()
        for depto in args.zona or list(LOCALIDADES_BOOKING):
            print(f"\n=== {depto} ===")
            for loc in LOCALIDADES_BOOKING[depto]:
                buscar_localidad(pagina, depto, loc, prog)
        if not args.sin_detalle:
            leer_detalles(pagina, prog)
        nav.close()
    print(f"\nListo: {len(prog['alojamientos'])} alojamientos en datos/booking.json. Ahora corré: python3 exportar_excel.py")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCortado. El progreso quedó guardado; volvé a correr el mismo comando para seguir.")
        sys.exit(1)
