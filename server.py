#!/usr/bin/env python3
import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PUERTO = 3000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, 'state.json')
PUBLIC_DIR = os.path.join(BASE_DIR, 'public')

NOMBRES_INICIALES = ['Gómez', 'FAJ', 'Al Cable', 'Robert', 'Barry']

TIPOS_MIME = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css',
    '.js': 'application/javascript',
}


def estado_inicial():
    return {'stock': 100, 'contadores': {nombre: 0 for nombre in NOMBRES_INICIALES}}


def leer_estado():
    if not os.path.exists(STATE_FILE):
        estado = estado_inicial()
        guardar_estado(estado)
        return estado
    with open(STATE_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def guardar_estado(estado):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _enviar_json(self, data, status=200):
        cuerpo = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _leer_cuerpo(self):
        largo = int(self.headers.get('Content-Length', 0))
        if largo == 0:
            return {}
        try:
            return json.loads(self.rfile.read(largo))
        except json.JSONDecodeError:
            return {}

    def _servir_archivo(self, ruta):
        ruta_completa = os.path.join(PUBLIC_DIR, ruta.lstrip('/'))
        if not os.path.isfile(ruta_completa):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'No encontrado')
            return
        ext = os.path.splitext(ruta_completa)[1]
        with open(ruta_completa, 'rb') as f:
            contenido = f.read()
        self.send_response(200)
        self.send_header('Content-Type', TIPOS_MIME.get(ext, 'application/octet-stream'))
        self.send_header('Content-Length', str(len(contenido)))
        self.end_headers()
        self.wfile.write(contenido)

    def do_GET(self):
        if self.path == '/api/state':
            return self._enviar_json(leer_estado())
        ruta = '/index.html' if self.path == '/' else self.path
        self._servir_archivo(ruta)

    def do_POST(self):
        if self.path == '/api/sumar':
            datos = self._leer_cuerpo()
            estado = leer_estado()
            nombre = datos.get('nombre')
            if nombre not in estado['contadores']:
                return self._enviar_json({'error': 'nombre inválido'}, 400)
            estado['contadores'][nombre] += 1
            if estado['stock'] > 0:
                estado['stock'] -= 1
            guardar_estado(estado)
            return self._enviar_json(estado)

        if self.path == '/api/restar':
            datos = self._leer_cuerpo()
            estado = leer_estado()
            nombre = datos.get('nombre')
            if nombre not in estado['contadores']:
                return self._enviar_json({'error': 'nombre inválido'}, 400)
            if estado['contadores'][nombre] > 0:
                estado['contadores'][nombre] -= 1
                estado['stock'] += 1
            guardar_estado(estado)
            return self._enviar_json(estado)

        if self.path == '/api/reset':
            estado = estado_inicial()
            guardar_estado(estado)
            return self._enviar_json(estado)

        self.send_response(404)
        self.end_headers()


def ips_de_red():
    ips = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith('127.') and ip not in ips:
                ips.append(ip)
    except socket.gaierror:
        pass
    return ips


if __name__ == '__main__':
    server = ThreadingHTTPServer(('0.0.0.0', PUERTO), Handler)
    print('\n🍺 Contador de cervezas — Los Galgos')
    print('----------------------------------------')
    print(f'En esta compu:   http://localhost:{PUERTO}')
    for ip in ips_de_red():
        print(f'Desde el celu:   http://{ip}:{PUERTO}')
    print('----------------------------------------')
    print('Todos los celus deben estar en el mismo WiFi.\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
