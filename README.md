# Los Galgos 🐕 — Contador de Cervezas

App recreativa, sin conexión con nada más. Cuenta cuántas cervezas toma cada uno del grupo y cuántas quedan en la heladera (arranca en 100).

## Cómo correrla

Usa Python 3, que ya viene instalado en Mac (no hace falta instalar nada más).

1. Abrí la Terminal en esta carpeta.
2. Corré:
   ```
   python3 server.py
   ```
3. La consola te va a mostrar dos direcciones:
   - Una para abrir en la compu (`localhost`)
   - Una para abrir desde los celus (la IP de la red, por ejemplo `192.168.1.23:3000`)

## Para usarla desde los celulares

Todos los celus tienen que estar conectados al **mismo WiFi** que la compu donde corre el servidor. Ahí entran a la dirección de red que te muestra la consola (ej: `http://192.168.1.23:3000`) desde el navegador del celu.

El contador se sincroniza solo cada 2 segundos, así que todos ven lo mismo casi en tiempo real.

## Botón "Reiniciar noche"

Vuelve todos los contadores a 0 y el stock a 100.
