from flask import Flask, jsonify, request, send_from_directory
import json
import os

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, 'state.json')

NOMBRES_INICIALES = ['Gómez', 'FAJ', 'Al Cable', 'Robert', 'Barry']


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


@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/api/state')
def api_state():
    return jsonify(leer_estado())


@app.route('/api/sumar', methods=['POST'])
def api_sumar():
    datos = request.get_json(silent=True) or {}
    nombre = datos.get('nombre')
    estado = leer_estado()
    if nombre not in estado['contadores']:
        return jsonify({'error': 'nombre inválido'}), 400
    estado['contadores'][nombre] += 1
    if estado['stock'] > 0:
        estado['stock'] -= 1
    guardar_estado(estado)
    return jsonify(estado)


@app.route('/api/restar', methods=['POST'])
def api_restar():
    datos = request.get_json(silent=True) or {}
    nombre = datos.get('nombre')
    estado = leer_estado()
    if nombre not in estado['contadores']:
        return jsonify({'error': 'nombre inválido'}), 400
    if estado['contadores'][nombre] > 0:
        estado['contadores'][nombre] -= 1
        estado['stock'] += 1
    guardar_estado(estado)
    return jsonify(estado)


@app.route('/api/reset', methods=['POST'])
def api_reset():
    estado = estado_inicial()
    guardar_estado(estado)
    return jsonify(estado)
