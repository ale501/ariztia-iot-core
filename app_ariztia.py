import os
import random
import threading
import time
from collections import deque
from datetime import datetime

import database
database.inicializar_bd()

from flask import Flask, jsonify, send_from_directory, Response, request
from prometheus_client import Gauge, Counter, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)
CARPETA = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Parámetros de Medición y Muestreo
# ---------------------------------------------------------------------------
INTERVALO_SEGUNDOS_OBJETIVO = 60   # Muestreo objetivo cada 60 segundos
TIMEOUT_DESCONEXION = 120         # 2 ciclos sin señal = desconectado
HISTORIAL_MAX = 100               # Cuántas lecturas se guardan para la tabla

# Rangos de prueba según requerimientos
RANGOS = {
    "normal": {
        "temp": (22.0, 25.5),
        "hum": (45.0, 55.0),
        "desc": "Confort normal (22–25.5 °C)"
    },
    "rango_27_30": {
        "temp": (27.0, 30.0),
        "hum": (50.0, 65.0),
        "desc": "Ensayo advertencia (27–30 °C)"
    },
    "critico_35": {
        "temp": (35.5, 41.0),
        "hum": (60.0, 75.0),
        "desc": "Ensayo crítico (>35 °C)"
    }
}

# ---------------------------------------------------------------------------
# Métricas Prometheus
# ---------------------------------------------------------------------------
metrica_temperatura = Gauge("ariztia_temperatura_celsius", "Temperatura del pabellón en Celsius")
metrica_humedad = Gauge("ariztia_humedad_relativa_pct", "Humedad relativa del pabellón (%)")
metrica_iec = Gauge("ariztia_iec", "Índice de Estrés Calórico (temperatura + humedad)")
metrica_nivel = Gauge("ariztia_nivel_alerta", "0=confort 1=precaución 2=estrés 3=crítico")
metrica_conexion = Gauge("ariztia_conexion_activa", "1=Conectado y transmitiendo, 0=Desconectado/Intermitente")
contador_invalidas = Counter("ariztia_lecturas_invalidas_total", "Total de lecturas inválidas o corruptas filtradas")

NIVEL_A_NUMERO = {"confort": 0, "precaucion": 1, "estres": 2, "critico": 3}


def clasificar_iec(iec: float):
    """Devuelve (nivel, etiqueta, accion) según la Tabla de Estrés Calórico."""
    if iec < 95:
        return "confort", "Confort", "Registro normal"
    if iec < 105:
        return "precaucion", "Precaución (27–30 °C)", "Notificación preventiva y activar ventilación"
    if iec <= 110:
        return "estres", "Estrés calórico", "Alerta con acuse de recibo obligatorio"
    return "critico", "Crítico (>35 °C)", "Escalamiento inmediato + protocolo de emergencia"


def validar_lectura_fisica(temp, hum):
    """
    Ensayo de Lecturas Inválidas:
    Verifica que los datos cumplan límites físicos de un galpón (0–55 °C, 10–100 % HR).
    """
    try:
        temp = float(temp)
        hum = float(hum)
    except (ValueError, TypeError):
        return False, "Valores no numéricos o incompletos"

    if not (0.0 <= temp <= 55.0):
        return False, f"Temperatura fuera de rango físico plausible: {temp} °C"
    if not (10.0 <= hum <= 100.0):
        return False, f"Humedad fuera de rango físico plausible: {hum} %"

    return True, "OK"


class SimuladorAriztia:
    def __init__(self):
        self.lock = threading.Lock()
        self.historial = deque(maxlen=HISTORIAL_MAX)
        self.actual = None
        self.running = True

        # Configuración de muestreo
        self.intervalo = INTERVALO_SEGUNDOS_OBJETIVO  # 60 segundos
        self.modo_escenario = "normal"  # "normal", "rango_27_30", "critico_35", "invalidas", "intermitente"
        self.ultima_lectura_real_ts = 0.0
        self.estado_conexion = "Conectado"

    def set_escenario(self, modo: str):
        with self.lock:
            self.modo_escenario = modo

    def set_intervalo(self, segundos: int):
        with self.lock:
            self.intervalo = max(1, int(segundos))

    def registrar_lectura_real(self, temp, hum):
        """Procesa datos reales enviados por hardware (Arduino / ESP32)."""
        valido, motivo = validar_lectura_fisica(temp, hum)
        ahora_ts = time.time()
        fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not valido:
            contador_invalidas.inc()
            registro_error = {
                "timestamp": ahora_ts,
                "fecha_hora": fecha_hora,
                "temperatura": temp,
                "humedad": hum,
                "iec": 0,
                "nivel": "error",
                "etiqueta": "Lectura Inválida",
                "accion": f"Descartada: {motivo}",
                "origen": "arduino",
                "estado_conexion": "Conectado (Dato Corrupto)"
            }
            with self.lock:
                self.actual = registro_error
                self.historial.append(registro_error)
            return False, motivo

        self.ultima_lectura_real_ts = ahora_ts
        lectura = self._procesar(float(temp), float(hum), origen="arduino", estado="Conectado")
        return True, lectura

    def _procesar(self, temp, hum, origen="simulado", estado="Conectado"):
        iec = round(temp + hum, 1)
        nivel, etiqueta, accion = clasificar_iec(iec)
        ahora_ts = time.time()
        fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Actualiza métricas Prometheus
        metrica_temperatura.set(temp)
        metrica_humedad.set(hum)
        metrica_iec.set(iec)
        metrica_nivel.set(NIVEL_A_NUMERO.get(nivel, 0))
        metrica_conexion.set(1)

        lectura = {
            "timestamp": ahora_ts,
            "fecha_hora": fecha_hora,
            "temperatura": temp,
            "humedad": hum,
            "iec": iec,
            "nivel": nivel,
            "etiqueta": etiqueta,
            "accion": accion,
            "origen": origen,
            "estado_conexion": estado
        }

        with self.lock:
            self.actual = lectura
            self.historial.append(lectura)
            self.estado_conexion = estado

        # Guardar en base de datos (PostgreSQL / SQLite) para que Grafana pueda mostrar tablas SQL
        try:
            database.guardar_lectura_ambiental(
                temp=temp,
                hum=hum,
                iec=iec,
                nivel=nivel,
                etiqueta=etiqueta,
                accion=accion,
                origen=origen,
                estado_conexion=estado
            )
        except Exception:
            pass

        return lectura

    def generar_lectura_ensayo(self):
        """Genera datos según el escenario seleccionado para pruebas."""
        ahora_ts = time.time()
        fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Ensayo: Conexión intermitente
        if self.modo_escenario == "intermitente":
            metrica_conexion.set(0)
            lectura_intermitente = {
                "timestamp": ahora_ts,
                "fecha_hora": fecha_hora,
                "temperatura": None,
                "humedad": None,
                "iec": None,
                "nivel": "critico",
                "etiqueta": "DESCONECTADO",
                "accion": "Pérdida de señal / timeout de conexión con el sensor",
                "origen": "simulado",
                "estado_conexion": "Desconectado"
            }
            with self.lock:
                self.actual = lectura_intermitente
                self.historial.append(lectura_intermitente)
                self.estado_conexion = "Desconectado"
            return lectura_intermitente

        # Ensayo: Lecturas inválidas (falla física de sensor)
        if self.modo_escenario == "invalidas":
            contador_invalidas.inc()
            temp_invalida = random.choice([-99.9, 125.0, 999.0])
            hum_invalida = random.choice([-10.0, 150.0, 250.0])
            valido, motivo = validar_lectura_fisica(temp_invalida, hum_invalida)

            lectura_invalida = {
                "timestamp": ahora_ts,
                "fecha_hora": fecha_hora,
                "temperatura": temp_invalida,
                "humedad": hum_invalida,
                "iec": 0,
                "nivel": "error",
                "etiqueta": "Lectura Inválida",
                "accion": f"Alerta sensor: {motivo}",
                "origen": "simulado",
                "estado_conexion": "Conectado (Lectura Inválida)"
            }
            with self.lock:
                self.actual = lectura_invalida
                self.historial.append(lectura_invalida)
                self.estado_conexion = "Conectado (Lectura Inválida)"
            return lectura_invalida

        # Ensayos térmicos: 27-30 °C, >35 °C o Confort
        cfg = RANGOS.get(self.modo_escenario, RANGOS["normal"])
        temp = round(random.uniform(*cfg["temp"]), 1)
        hum = round(random.uniform(*cfg["hum"]), 1)
        return self._procesar(temp, hum, origen="simulado", estado="Conectado")

    def loop(self):
        """Ciclo continuo de muestreo (cada 60 segundos por defecto)."""
        while self.running:
            hace = time.time() - self.ultima_lectura_real_ts
            if hace >= self.intervalo:
                self.generar_lectura_ensayo()

            dormido = 0
            while dormido < self.intervalo and self.running:
                time.sleep(1)
                dormido += 1

    def get_estado(self):
        with self.lock:
            return {
                "actual": self.actual,
                "historial": list(self.historial),
                "modo_escenario": self.modo_escenario,
                "intervalo_segundos": self.intervalo,
                "estado_conexion": self.estado_conexion
            }

    def reiniciar(self):
        with self.lock:
            self.historial.clear()
            self.actual = None
            self.modo_escenario = "normal"
            self.ultima_lectura_real_ts = 0.0


servicio = SimuladorAriztia()
hilo = threading.Thread(target=servicio.loop, daemon=True)
hilo.start()


# ---------------------------------------------------------------------------
# Rutas Flask
# ---------------------------------------------------------------------------

@app.route("/ariztia_data")
def ariztia_data():
    return jsonify(servicio.get_estado())


@app.route("/ariztia_set_escenario", methods=["POST", "GET"])
def ariztia_set_escenario():
    """Cambia el escenario: normal, rango_27_30, critico_35, invalidas, intermitente"""
    tipo = request.args.get("tipo") or (request.json or {}).get("tipo", "normal")
    servicio.set_escenario(tipo)
    lectura = servicio.generar_lectura_ensayo()
    return jsonify({"ok": True, "modo_escenario": tipo, "lectura": lectura})


@app.route("/ariztia_set_intervalo", methods=["POST", "GET"])
def ariztia_set_intervalo():
    """Configura el intervalo (ej: 60s o 3s demo)"""
    segs = request.args.get("segundos", 60)
    try:
        segs = int(segs)
    except ValueError:
        segs = 60
    servicio.set_intervalo(segs)
    return jsonify({"ok": True, "intervalo_segundos": segs})


@app.route("/ariztia_forzar_lectura", methods=["POST", "GET"])
def ariztia_forzar_lectura():
    """Fuerza una lectura inmediata sin esperar el intervalo."""
    lectura = servicio.generar_lectura_ensayo()
    return jsonify({"ok": True, "lectura": lectura})


@app.route("/ariztia_lectura", methods=["POST"])
def ariztia_lectura():
    """Recibe {"temperatura": .., "humedad": ..} desde hardware real."""
    data = request.get_json(silent=True) or {}
    temp = data.get("temperatura")
    hum = data.get("humedad")

    if temp is None or hum is None:
        return jsonify({"ok": False, "error": "Faltan parámetros 'temperatura' y 'humedad'"}), 400

    ok, resultado = servicio.registrar_lectura_real(temp, hum)
    if not ok:
        return jsonify({"ok": False, "error": f"Lectura inválida descartada: {resultado}"}), 422

    return jsonify({"ok": True, "lectura": resultado})


@app.route("/ariztia_reiniciar", methods=["POST"])
def ariztia_reiniciar():
    servicio.reiniciar()
    return jsonify({"ok": True})


@app.route("/")
def index():
    return send_from_directory(CARPETA, "ariztia.html")


@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.route("/styles.css")
def estilos():
    return send_from_directory(CARPETA, "styles.css")


if __name__ == "__main__":
    print("=" * 60)
    print("SISTEMA DE MONITOREO AMBIENTAL - ARIZTÍA")
    print("Muestreo objetivo: cada 60 segundos")
    print("Ensayos disponibles: 27–30 °C, >35 °C, Lecturas Inválidas, Intermitencia")
    print("Dashboard web: http://127.0.0.1:5001")
    print("Métricas Prometheus: http://127.0.0.1:5001/metrics")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)