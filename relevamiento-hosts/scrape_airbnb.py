"""Relevamiento de anuncios de Airbnb en Montevideo, Maldonado y Rocha.

Recorre el mapa por cuadrículas (las divide si tienen demasiados resultados),
junta los anuncios y después entra a cada uno para leer los datos públicos del
anfitrión. Guarda el progreso en datos/airbnb.json: si se corta, se vuelve a
correr y sigue donde quedó.

Uso:
    python3 scrape_airbnb.py                  # los tres departamentos
    python3 scrape_airbnb.py --zona Rocha     # solo uno
    python3 scrape_airbnb.py --sin-detalle    # solo la búsqueda, sin entrar a cada anuncio
"""
import argparse
import re
import sys
from urllib.parse import urlencode

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

from comun import ZONAS, cargar_progreso, departamento_por_coordenadas, guardar_progreso, pausa

BASE = "https://www.airbnb.com.uy"
MAX_PAGINAS = 15          # Airbnb no muestra más de 15 páginas por búsqueda
UMBRAL_DIVIDIR = 250      # si una cuadrícula supera esto, se parte en 4
LADO_MINIMO = 0.01        # grados (~1 km): no se divide más allá
PROFUNDIDAD_MAX = 7       # tope de divisiones sucesivas de una cuadrícula

# Extrae las tarjetas de resultados de la página de búsqueda.
JS_TARJETAS = r"""
() => {
  const salida = [];
  const vistos = new Set();
  const enlaces = document.querySelectorAll('a[href*="/rooms/"]');
  for (const a of enlaces) {
    const m = a.getAttribute('href').match(/\/rooms\/(?:plus\/)?(\d+)/);
    if (!m || vistos.has(m[1])) continue;
    const tarjeta = a.closest('[data-testid="card-container"]') || a.closest('[itemprop="itemListElement"]') || a.parentElement;
    if (!tarjeta) continue;
    vistos.add(m[1]);
    const texto = (sel) => { const e = tarjeta.querySelector(sel); return e ? e.innerText.trim() : ''; };
    const meta = (prop) => { const e = tarjeta.querySelector(`meta[itemprop="${prop}"]`); return e ? e.content : ''; };
    salida.push({
      id: m[1],
      titulo: texto('[data-testid="listing-card-title"]') || meta('name'),
      subtitulo: [...tarjeta.querySelectorAll('[data-testid="listing-card-subtitle"]')].map(e => e.innerText.trim()).join(' | '),
      nombre_anuncio: meta('name'),
      texto: tarjeta.innerText.replace(/\s+/g, ' ').trim(),
    });
  }
  return salida;
}
"""

# Extrae datos públicos del anuncio y del anfitrión en la página de detalle.
JS_DETALLE = r"""
() => {
  const html = document.documentElement.innerHTML;
  const cuerpo = document.body.innerText;
  const r = {};
  const ll = html.match(/"lat":\s*(-?\d+\.\d+),\s*"lng":\s*(-?\d+\.\d+)/);
  if (ll) { r.lat = parseFloat(ll[1]); r.lng = parseFloat(ll[2]); }
  const perfil = document.querySelector('a[href*="/users/show/"], a[href*="/users/profile/"]');
  if (perfil) {
    r.host_url = new URL(perfil.getAttribute('href'), location.origin).href.split('?')[0];
    const id = r.host_url.match(/\/users\/(?:show|profile)\/(\d+)/);
    if (id) r.host_id = id[1];
  }
  const anfitrion = cuerpo.match(/(?:Anfitri[oó]n|Anfitriona|Hosted by)\s*:?\s*([^\n]+)/);
  if (anfitrion) r.host_nombre = anfitrion[1].split(/\s[·•|]\s|Superanfitri|Superhost|\d+\s+(?:años|meses|years|months)/)[0].trim().slice(0, 60);
  r.superhost = /Superanfitri[oó]n|Superhost/.test(cuerpo);
  const anios = cuerpo.match(/(\d+)\s+(?:años|año|years?)\s+(?:como anfitri[oó]n|hosting)/i);
  if (anios) r.host_anios = parseInt(anios[1]);
  const meses = cuerpo.match(/(\d+)\s+(?:meses|mes|months?)\s+(?:como anfitri[oó]n|hosting)/i);
  if (meses && !anios) r.host_anios = 0;
  const h1 = document.querySelector('h1');
  if (h1) r.nombre_anuncio = h1.innerText.trim();
  const h2 = [...document.querySelectorAll('h2')].map(e => e.innerText.trim()).find(t => /\b(en|in)\b/.test(t) && /(Alojamiento|Casa|Departamento|Habitaci|Cabaña|Apartamento|home|apartment|room|house|cabin|condo|guest|unit|place)/i.test(t));
  if (h2) r.tipo_y_zona = h2;
  const caract = cuerpo.match(/(\d+)\s+(?:huéspedes|huésped|guests?)[^\n]*/i);
  if (caract) r.capacidad = caract[0].trim();
  const nota = cuerpo.match(/(?:Calificaci[oó]n|Rated)\s+(\d[.,]\d+)/i) || cuerpo.match(/★\s*(\d[.,]\d+)/);
  if (nota) r.calificacion = parseFloat(nota[1].replace(',', '.'));
  const resenas = cuerpo.match(/(\d[\d.,]*)\s+(?:evaluaciones|reseñas|reviews)/i);
  if (resenas) r.resenas = parseInt(resenas[1].replace(/[.,]/g, ''));
  const licencia = cuerpo.match(/(?:N[uú]mero de registro|Registration number|Licencia)\s*:?\s*([^\n]+)/i);
  if (licencia) r.registro = licencia[1].trim();
  return r;
}
"""

# Lee el total de resultados que informa Airbnb ("Más de 1.000 alojamientos", "245 places"...).
JS_TOTAL = r"""
() => {
  const t = document.body.innerText;
  const m = t.match(/(M[aá]s de|Over)?\s*(\d[\d.,]*)\+?\s+(?:alojamientos|places|stays|homes|lugares)/i);
  if (!m) return null;
  const n = parseInt(m[2].replace(/[.,]/g, ''));
  return m[1] ? Math.max(n, 1001) : n;
}
"""


def url_busqueda(s, o, n, e):
    params = {
        "ne_lat": n, "ne_lng": e, "sw_lat": s, "sw_lng": o,
        "search_by_map": "true", "search_type": "user_map_move",
        "zoom_level": 14, "locale": "es",
    }
    return f"{BASE}/s/Uruguay/homes?{urlencode(params)}"


def parse_tarjeta(t):
    """Saca calificación, reseñas y precio del texto libre de la tarjeta."""
    texto = t.get("texto", "")
    r = {}
    m = re.search(r"(\d[.,]\d{1,2})\s*\((\d[\d.,]*)\)", texto)
    if m:
        r["calificacion"] = float(m.group(1).replace(",", "."))
        r["resenas"] = int(re.sub(r"[.,]", "", m.group(2)))
    elif re.search(r"\bNuevo\b|\bNew\b", texto):
        r["calificacion"] = "Nuevo"
    m = re.search(r"((?:US|UYU|U)?\$\s?[\d.,]+)\s*(?:US|UYU)?\s*(?:por noche|noche|night)", texto)
    if m:
        r["precio_noche"] = m.group(1)
    r["superhost_tarjeta"] = bool(re.search(r"Superanfitri|Superhost", texto))
    r["favorito_huespedes"] = bool(re.search(r"Favorito entre huéspedes|Guest favorite", texto))
    return r


def esperar_resultados(pagina):
    try:
        pagina.wait_for_selector('a[href*="/rooms/"]', timeout=25000)
        return True
    except PWTimeout:
        return False


def detectar_bloqueo(pagina):
    texto = pagina.inner_text("body")[:3000].lower()
    return any(p in texto for p in ("captcha", "verifica que eres humano", "are you a human", "access denied"))


def cerrar_popups(pagina):
    for etiqueta in ("Cerrar", "Close", "Aceptar", "Accept", "OK"):
        try:
            boton = pagina.get_by_role("button", name=etiqueta, exact=True)
            if boton.count() and boton.first.is_visible():
                boton.first.click(timeout=1500)
        except Exception:
            pass


def recorrer_celda(pagina, depto, celda, prog, profundidad=0):
    s, o, n, e = celda
    clave = f"{depto}|{s:.4f},{o:.4f},{n:.4f},{e:.4f}"
    if clave in prog["celdas_hechas"]:
        return
    pagina.goto(url_busqueda(s, o, n, e), wait_until="domcontentloaded", timeout=60000)
    pausa()
    cerrar_popups(pagina)
    if detectar_bloqueo(pagina):
        print("\n⚠️  Airbnb pidió verificación (captcha). Resolvelo en la ventana del navegador y apretá Enter acá.")
        input()
    if not esperar_resultados(pagina):
        print(f"  {clave}: sin resultados")
        prog["celdas_hechas"].append(clave)
        return
    total = pagina.evaluate(JS_TOTAL)
    if total and total > UMBRAL_DIVIDIR and (n - s) > LADO_MINIMO and profundidad < PROFUNDIDAD_MAX:
        print(f"  {clave}: ~{total} resultados → divido en 4")
        lat_m, lng_m = (s + n) / 2, (o + e) / 2
        for sub in ((s, o, lat_m, lng_m), (s, lng_m, lat_m, e), (lat_m, o, n, lng_m), (lat_m, lng_m, n, e)):
            recorrer_celda(pagina, depto, sub, prog, profundidad + 1)
        prog["celdas_hechas"].append(clave)
        guardar_progreso("airbnb", prog)
        return

    nuevos = 0
    vistos_celda = set()
    for num in range(1, MAX_PAGINAS + 1):
        tarjetas = pagina.evaluate(JS_TARJETAS)
        ids = {t["id"] for t in tarjetas}
        if not ids - vistos_celda:
            break  # la página no trajo nada distinto: se terminó la paginación
        vistos_celda |= ids
        for t in tarjetas:
            if t["id"] not in prog["anuncios"]:
                nuevos += 1
                t.update(parse_tarjeta(t))
                t["zona_busqueda"] = depto
                t["url"] = f"{BASE}/rooms/{t['id']}"
                prog["anuncios"][t["id"]] = t
        siguiente = pagina.locator('a[aria-label="Siguiente"], a[aria-label="Next"]')
        if not siguiente.count() or siguiente.first.get_attribute("aria-disabled") == "true":
            break
        siguiente.first.click()
        pausa()
        esperar_resultados(pagina)
    print(f"  {clave}: total informado {total}, {nuevos} anuncios nuevos (acumulado {len(prog['anuncios'])})")
    prog["celdas_hechas"].append(clave)
    guardar_progreso("airbnb", prog)


def leer_detalles(pagina, prog):
    pendientes = [a for a in prog["anuncios"].values() if not a.get("detalle_ok")]
    print(f"\nLeyendo detalle de {len(pendientes)} anuncios...")
    for i, a in enumerate(pendientes, 1):
        try:
            pagina.goto(a["url"] + "?locale=es", wait_until="domcontentloaded", timeout=60000)
            pagina.wait_for_selector("h1", timeout=20000)
            pausa(1.5, 3.5)
            cerrar_popups(pagina)
            if detectar_bloqueo(pagina):
                print("\n⚠️  Airbnb pidió verificación. Resolvelo en el navegador y apretá Enter acá.")
                input()
            # La sección del anfitrión carga al bajar.
            pagina.mouse.wheel(0, 6000)
            pausa(1.0, 2.0)
            det = pagina.evaluate(JS_DETALLE)
            for k, v in det.items():
                if v not in (None, "") and (k not in a or k in ("lat", "lng", "nombre_anuncio")):
                    a[k] = v
            a["departamento"] = departamento_por_coordenadas(a.get("lat"), a.get("lng")) or a["zona_busqueda"]
            a["detalle_ok"] = True
        except PWTimeout:
            a["error"] = "timeout"
        except Exception as ex:  # noqa: BLE001 - se registra y se sigue con el siguiente
            a["error"] = str(ex)[:200]
        if i % 10 == 0:
            guardar_progreso("airbnb", prog)
            print(f"  {i}/{len(pendientes)}")
    guardar_progreso("airbnb", prog)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zona", choices=list(ZONAS), action="append")
    ap.add_argument("--sin-detalle", action="store_true")
    ap.add_argument("--headless", action="store_true", help="sin ventana (más probable que bloqueen)")
    args = ap.parse_args()

    prog = cargar_progreso("airbnb") or {}
    prog.setdefault("anuncios", {})
    prog.setdefault("celdas_hechas", [])

    with sync_playwright() as pw:
        nav = pw.chromium.launch(headless=args.headless)
        ctx = nav.new_context(locale="es-UY", timezone_id="America/Montevideo",
                              viewport={"width": 1400, "height": 900})
        pagina = ctx.new_page()
        for depto in args.zona or list(ZONAS):
            print(f"\n=== {depto} ===")
            recorrer_celda(pagina, depto, ZONAS[depto], prog)
        if not args.sin_detalle:
            leer_detalles(pagina, prog)
        nav.close()
    print(f"\nListo: {len(prog['anuncios'])} anuncios en datos/airbnb.json. Ahora corré: python3 exportar_excel.py")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCortado. El progreso quedó guardado; volvé a correr el mismo comando para seguir.")
        sys.exit(1)
