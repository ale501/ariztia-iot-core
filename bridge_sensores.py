"""
PUENTE DE COMUNICACIÓN SERIE USB PARA ESP32 / ARDUINO
======================================================
Lee las mediciones de temperatura y humedad enviadas por el ESP32
a través del cable USB y las reenvía automáticamente al backend
de Ariztía (http://localhost:5001/ariztia_lectura).
"""

import json
import os
import re
import sys
import time
import requests
import serial
import serial.tools.list_ports

CARPETA = os.path.dirname(os.path.abspath(__file__))
RUTA_CONFIG = os.path.join(CARPETA, "config_hardware.json")


def cargar_config():
    cfg = {
        "puerto_com": "AUTO",
        "baud_rate": 115200,
        "url_servidor": "http://127.0.0.1:5001/ariztia_lectura"
    }
    if os.path.exists(RUTA_CONFIG):
        try:
            with open(RUTA_CONFIG, "r", encoding="utf-8") as f:
                datos = json.load(f)
                seccion = datos.get("sensores_esp32", {})
                cfg["puerto_com"] = seccion.get("puerto_com", "AUTO")
                cfg["baud_rate"] = int(seccion.get("baud_rate", 115200))
                cfg["url_servidor"] = seccion.get("url_servidor_ariztia", cfg["url_servidor"])
        except Exception as e:
            print(f"[CONFIG AVISO] Error leyendo config_hardware.json: {e}")
    return cfg


def detectar_puerto_esp32(puerto_preferido="AUTO"):
    """
    Busca puertos COM activos. Si puerto_preferido es distinto de AUTO, lo prueba.
    Si es AUTO, busca adaptadores USB comúnmente usados por ESP32 / Arduino (CP210x, CH340, FTDI, etc.).
    """
    puertos = list(serial.tools.list_ports.comports())
    if not puertos:
        return None

    if puerto_preferido and puerto_preferido.upper() != "AUTO":
        for p in puertos:
            if p.device.upper() == puerto_preferido.upper():
                return p.device

    # Palabras clave habituales de chips USB-Serial en ESP32
    chips_conocidos = ["CP210", "CH340", "CH910", "FTDI", "USB-SERIAL", "UART", "SILICON LABS"]
    for p in puertos:
        desc = (p.description or "").upper()
        hwid = (p.hwid or "").upper()
        for chip in chips_conocidos:
            if chip in desc or chip in hwid:
                return p.device

    # Si hay un único puerto COM USB disponible, usarlo
    return puertos[0].device


def extraer_datos_linea(linea):
    """
    Acepta varios formatos emitidos por el ESP32:
    1. JSON: {"temperatura": 26.5, "humedad": 58.0}
    2. CSV:  26.5, 58.0
    3. Texto: T: 26.5 H: 58.0
    """
    linea = linea.strip()
    if not linea:
        return None

    # Caso 1: JSON
    if linea.startswith("{") and linea.endswith("}"):
        try:
            d = json.loads(linea)
            t = float(d.get("temperatura", d.get("temp", 0)))
            h = float(d.get("humedad", d.get("hum", 0)))
            return t, h
        except Exception:
            pass

    # Caso 2: CSV simple (26.5, 58.2)
    partes = linea.split(",")
    if len(partes) == 2:
        try:
            return float(partes[0].strip()), float(partes[1].strip())
        except ValueError:
            pass

    # Caso 3: Búsqueda por expresiones regulares
    match_t = re.search(r"temp[a-z]*[:= ]+([0-9.]+)", linea, re.IGNORECASE)
    match_h = re.search(r"hum[a-z]*[:= ]+([0-9.]+)", linea, re.IGNORECASE)
    if match_t and match_h:
        try:
            return float(match_t.group(1)), float(match_h.group(1))
        except ValueError:
            pass

    return None


def ejecutar_puente():
    print("=" * 60)
    print("PUENTE USB/SERIAL - SENSORES ESP32 ARIZTÍA")
    print("=" * 60)

    conexion = None
    ultimo_intento_busqueda = 0

    while True:
        try:
            cfg = cargar_config()
            puerto_cfg = cfg["puerto_com"]
            baud = cfg["baud_rate"]
            url_api = cfg["url_servidor"]

            # 1. Si no hay conexión activa, intentar conectar
            if conexion is None:
                ahora = time.time()
                if ahora - ultimo_intento_busqueda >= 4:
                    ultimo_intento_busqueda = ahora
                    puerto = detectar_puerto_esp32(puerto_cfg)

                    if puerto:
                        print(f"[CONECTANDO] Encontrado dispositivo en {puerto}. Abriendo a {baud} baudios...")
                        try:
                            conexion = serial.Serial(puerto, baud, timeout=1.5)
                            time.sleep(2)  # El ESP32 puede reiniciarse al abrir el DTR
                            print(f"[OK] Conectado exitosamente a ESP32 en {puerto}.")
                        except Exception as err:
                            print(f"[AVISO] No se pudo abrir {puerto}: {err}")
                            conexion = None
                    else:
                        disponibles = [p.device for p in serial.tools.list_ports.comports()]
                        disp_str = ", ".join(disponibles) if disponibles else "ninguno"
                        print(f"[ESPERA] Buscando ESP32... Puertos COM detectados: [{disp_str}]. Config: {puerto_cfg}")

                time.sleep(0.5)
                continue

            # 2. Leer datos si la conexión está abierta
            if conexion.in_waiting > 0:
                linea = conexion.readline().decode("utf-8", errors="ignore").strip()
                if not linea:
                    continue

                datos = extraer_datos_linea(linea)
                if datos:
                    temp, hum = datos
                    print(f"-> [ESP32 USB] Temp: {temp:.1f} °C | Humedad: {hum:.1f} %")

                    # Reenviar al servidor de monitoreo
                    try:
                        res = requests.post(url_api, json={"temperatura": temp, "humedad": hum}, timeout=2.5)
                        if res.status_code == 200:
                            print("   [BACKEND OK] Lectura registrada correctamente.")
                        else:
                            print(f"   [BACKEND ERROR] Código {res.status_code}: {res.text}")
                    except requests.exceptions.RequestException as req_err:
                        print(f"   [BACKEND ERROR] Servidor {url_api} inaccesible: {req_err}")
                else:
                    # Línea de depuración o log del ESP32
                    print(f"[ESP32 LOG]: {linea}")

            time.sleep(0.05)

        except (serial.SerialException, OSError) as ser_err:
            print(f"[DESCONEXIÓN] Se perdió la comunicación con el ESP32: {ser_err}")
            if conexion:
                try:
                    conexion.close()
                except Exception:
                    pass
            conexion = None
            time.sleep(2)

        except KeyboardInterrupt:
            print("\n[SALIR] Deteniendo puente de sensores.")
            if conexion:
                try:
                    conexion.close()
                except Exception:
                    pass
            break


if __name__ == "__main__":
    ejecutar_puente()
