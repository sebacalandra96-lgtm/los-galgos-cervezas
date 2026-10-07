# Relevamiento de alojamientos: Montevideo, Maldonado y Rocha

## Qué hay en esta carpeta

| Archivo | Para qué |
|---|---|
| `base_hosts_uruguay.xlsx` | El Excel. Ya trae las hojas **Resumen** (tamaño del mercado) y **Canales** (inmobiliarias, asociaciones y grupos para contactar). Las hojas Airbnb y Booking se llenan al correr el relevamiento. |
| `correr.command` | Doble clic y corre todo: instala, releva Booking y Airbnb y arma el Excel. |
| `mensajes_contacto.md` | Textos listos para inmobiliarias, posadas, grupos y asociaciones. |
| `landing/index.html` | Página para que los anfitriones se anoten, con calculadora de ahorro y consentimiento. |

## Cómo correrlo (Mac)

1. Descomprimí la carpeta donde quieras (por ejemplo, en el Escritorio).
2. La primera vez, abrí la Terminal, escribí `chmod +x ` (con un espacio al final), arrastrá `correr.command` a la ventana y apretá Enter. Después, clic derecho → **Abrir** sobre `correr.command`. macOS pide confirmar porque el archivo no viene de la App Store.
3. Se abre un navegador que va solo. **No lo cierres ni lo uses.** Podés minimizarlo.
4. Si Airbnb o Booking piden un captcha, la Terminal avisa: lo resolvés en la ventana del navegador y apretás Enter en la Terminal.
5. Al final se abre el Excel.

**Tiempo estimado:** varias horas. Hay unos 10.000 anuncios en la zona y el script va despacio a propósito para que no lo bloqueen. Si se corta, se cierra la tapa de la compu o lo cancelás con Ctrl+C, volvé a abrir `correr.command` y sigue donde quedó: el progreso queda guardado en `datos/`.

## Teléfonos comerciales de alojamientos (opcional, recomendado)

Booking no muestra teléfonos. El script `enriquecer_google.py` busca cada alojamiento de Booking en Google Maps con la API oficial y trae su teléfono comercial, su web y la ficha de Maps.

1. Entrá a https://console.cloud.google.com/, creá un proyecto y activá **Places API (New)**. Pide una tarjeta, pero Google da un crédito gratis mensual que alcanza para miles de búsquedas.
2. En **Credenciales**, creá una clave de API.
3. Guardala en un archivo `clave_google.txt` en esta carpeta, solo la clave.
4. La próxima vez que corras `correr.command`, se usa sola.

## Qué datos trae y qué no

- **Airbnb:** anuncio, tipo, capacidad, calificación, reseñas, precio y coordenadas. Del anfitrión, solo lo público: nombre de pila, perfil, si es Superanfitrión, años como anfitrión y **cuántos anuncios tiene**. La hoja **Airbnb - Anfitriones** ordena a los anfitriones de más a menos anuncios. Los de 3 o más casi siempre son administradoras o inversores, y son los que más rinden contactar.
- **Booking:** nombre, tipo, dirección, coordenadas, puntaje, reseñas, si es particular o profesional y, con Google, teléfono y web comercial.
- **No trae teléfonos ni emails de anfitriones particulares.** Las plataformas no los publican y no los buscamos por otras vías: la Ley 18.331 exige consentimiento para usarlos con fines comerciales. A esos anfitriones se llega por la landing, los grupos y las administradoras.

## Limitaciones

- Airbnb y Booking cambian sus páginas seguido. Si un día el script trae 0 resultados o columnas vacías, hay que actualizar los selectores: pasame el error y lo arreglo.
- Ninguna búsqueda garantiza el 100% de los anuncios. Las búsquedas se dividen en zonas chicas para acercarse lo más posible.
- Los términos de uso de Airbnb y Booking no permiten el relevamiento automatizado. Usalo para estudiar el mercado y con moderación, no lo corras en loop.
