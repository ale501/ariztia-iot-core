import glob
import http.server
import json
import os
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time
import webbrowser

CARPETA = os.path.dirname(os.path.abspath(__file__))
PUERTO_SITIO = 8000
URL_LOGIN = f"http://localhost:{PUERTO_SITIO}/login.html"

def obtener_interprete_python():
    """Detecta si existe un entorno virtual local (.venv) para usar sus dependencias."""
    if os.name == "nt":
        venv_py = os.path.join(CARPETA, ".venv", "Scripts", "python.exe")
    else:
        venv_py = os.path.join(CARPETA, ".venv", "bin", "python")
    if os.path.exists(venv_py):
        return venv_py
    return sys.executable

PYTHON = obtener_interprete_python()

procesos = []

# Puertos esperados por servicio
PUERTOS = {
    "Sitio web (Login/Menú)": PUERTO_SITIO,
    "Tracking de pollitos (prueba.py)": 5000,
    "Monitoreo Ariztía (app_ariztia.py)": 5001,
    "Servidor Prometheus": 9090,
    "Servidor Grafana": 3000
}


def puerto_ocupado(puerto):
    """Verifica si un puerto TCP local ya está en uso."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def buscar_ejecutable_prometheus():
    """Busca prometheus.exe en la carpeta actual, en subcarpetas o en el PATH."""
    # 1. En la misma carpeta
    directo = os.path.join(CARPETA, "prometheus.exe")
    if os.path.exists(directo):
        return directo

    # 2. En cualquier subcarpeta descargada (ej: prometheus-3.x.x...)
    coincidencias = glob.glob(os.path.join(CARPETA, "*prometheus*", "prometheus.exe"))
    if coincidencias:
        return coincidencias[0]

    # 3. En el PATH del sistema
    en_path = shutil.which("prometheus")
    return en_path


def buscar_ejecutable_grafana():
    """Busca grafana.exe o grafana-server.exe en subcarpetas, en Program Files o en el PATH."""
    for nombre_exe in ["grafana.exe", "grafana-server.exe"]:
        coincidencias = glob.glob(os.path.join(CARPETA, "*grafana*", "**", nombre_exe), recursive=True)
        if coincidencias:
            return coincidencias[0]

    for nombre_exe in ["grafana.exe", "grafana-server.exe"]:
        ruta_pf = os.path.join(r"C:\Program Files\GrafanaLabs\grafana\bin", nombre_exe)
        if os.path.exists(ruta_pf):
            return ruta_pf

    return shutil.which("grafana") or shutil.which("grafana-server")


def validar_entorno():
    """Valida los archivos base antes de levantar servicios."""
    print("-> Verificando entorno y puertos...")
    archivos_base = ["login.html", "menu.html", "styles.css", "ariztia.html", "app_ariztia.py", "prueba.py"]
    faltan = [f for f in archivos_base if not os.path.exists(os.path.join(CARPETA, f))]
    if faltan:
        print("[error] Faltan archivos esenciales en el proyecto:")
        for f in faltan:
            print("   -", f)
        return False

    # Verificar si hay puertos ocupados
    ocupados = [(nombre, p) for nombre, p in PUERTOS.items() if puerto_ocupado(p)]
    if ocupados:
        print("\n[aviso] Los siguientes puertos ya están ocupados:")
        for nombre, p in ocupados:
            print(f"   - Puerto {p} ({nombre})")
        print("   Si quedaron procesos abiertos, ciérralos desde el Administrador de Tareas")
        print("   o reinicia la terminal.\n")
    return True


def iniciar_proceso(comando, nombre, cwd=CARPETA):
    """Lanza un proceso en segundo plano y lo registra para cierre seguro."""
    try:
        proc = subprocess.Popen(comando, cwd=cwd)
        procesos.append((nombre, proc))
        print(f"   [OK] {nombre} iniciado.")
        return proc
    except Exception as e:
        print(f"   [ERROR] No se pudo iniciar {nombre}: {e}")
        return None


class ManejadorSinCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_POST(self):
        if self.path.startswith("/api/chatbot"):
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            try:
                data = json.loads(body)
            except Exception:
                data = {}
            msg = data.get("mensaje", "")
            try:
                import chatbot
                resultado = chatbot.responder_consulta(msg)
            except Exception as e:
                resultado = {"respuesta": f"⚠️ Error en asistente: {e}"}

            resp_bytes = json.dumps({"ok": True, "resultado": resultado}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp_bytes)
            return

        super().do_POST()


def iniciar_servidor_estatico():
    """Sirve login.html, menu.html, etc. en el puerto 8000 sin caché para evitar desincronizaciones."""
    os.chdir(CARPETA)
    handler = ManejadorSinCache
    socketserver.TCPServer.allow_reuse_address = True
    try:
        httpd = socketserver.TCPServer(("", PUERTO_SITIO), handler)
    except OSError as e:
        print(f"\n[error] El puerto {PUERTO_SITIO} ya está en uso ({e}).")
        return None

    hilo = threading.Thread(target=httpd.serve_forever, daemon=True)
    hilo.start()
    print(f"   [OK] Sitio web principal corriendo en http://localhost:{PUERTO_SITIO}/")
    return httpd


def detener_todo(httpd=None):
    """Cierra todos los procesos hijos sin dejar procesos huérfanos en Windows."""
    print("\nDeteniendo todos los servicios...")
    if httpd:
        try:
            httpd.shutdown()
        except Exception:
            pass

    for nombre, proc in procesos:
        if proc.poll() is None:
            try:
                # En Windows, taskkill /F /T termina el proceso y todos sus subprocesos
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                else:
                    proc.terminate()
            except Exception:
                proc.kill()
    print("[OK] Todos los servicios han sido detenidos.")


def main():
    print("=" * 65)
    print(" INICIADOR INTEGRAL DE PROYECTO (ARIZTÍA + TRACKING + GRAFANA)")
    print("=" * 65)

    if not validar_entorno():
        sys.exit(1)

    httpd = None

    try:
        print("\n1. Verificando e inicializando base de datos...")
        try:
            import database
            database.inicializar_bd()
        except Exception as e_bd:
            print(f"   [AVISO BD] {e_bd}")

        print("\n2. Iniciando Backends de Datos y Monitoreo...")
        # 1. Monitoreo Ariztía (Puerto 5001)
        iniciar_proceso([PYTHON, "app_ariztia.py"], "Monitoreo Ariztía (Puerto 5001)")

        # 2. Tracking de visión (Puerto 5000)
        iniciar_proceso([PYTHON, "prueba.py"], "Tracking Visión (Puerto 5000)")

        # 3. Módulo de Sensores Físicos (Preparado para cuando llegue el hardware)
        script_sensores = None
        for posible in ["bridge_sensores.py", "bridge_serial.py", "sensores_arduino.py"]:
            if os.path.exists(os.path.join(CARPETA, posible)):
                script_sensores = posible
                break

        if script_sensores:
            print("\n2. Hardware / Sensores Físicos:")
            iniciar_proceso([PYTHON, script_sensores], f"Puente de Sensores ({script_sensores})")
        else:
            print("\n2. Hardware / Sensores Físicos:")
            print("   [INFO] Modo simulación activo. Cuando lleguen los sensores físicos,")
            print("          basta con crear 'bridge_sensores.py' y se iniciará aquí automáticamente.")

        # 4. Prometheus (Puerto 9090 / 9091)
        print("\n3. Métricas y Dashboards:")
        if puerto_ocupado(9090) or puerto_ocupado(9091):
            pto_act = 9090 if puerto_ocupado(9090) else 9091
            print(f"   [INFO] Servidor Prometheus ya activo en puerto {pto_act} (Docker o local).")
        else:
            prom_exe = buscar_ejecutable_prometheus()
            if prom_exe:
                cfg_prom = os.path.join(CARPETA, "prometheus.yml")
                if not os.path.exists(cfg_prom):
                    cfg_prom = os.path.join(os.path.dirname(prom_exe), "prometheus.yml")

                iniciar_proceso([prom_exe, f"--config.file={cfg_prom}"], "Servidor Prometheus (Puerto 9090)")
            else:
                print("   [AVISO] No se encontró prometheus.exe. Recuerda descomprimirlo en la carpeta.")

        # 5. Grafana (Puerto 3000)
        if puerto_ocupado(3000):
            print("   [INFO] Servidor Grafana ya activo en puerto 3000 (ej: Docker o servicio previo).")
        else:
            grafana_exe = buscar_ejecutable_grafana()
            if grafana_exe:
                dir_grafana = os.path.dirname(os.path.dirname(grafana_exe))
                if os.path.basename(grafana_exe).lower() == "grafana.exe":
                    cmd_grafana = [grafana_exe, "server", f"--homepath={dir_grafana}"]
                else:
                    cmd_grafana = [grafana_exe, f"-homepath={dir_grafana}"]
                iniciar_proceso(cmd_grafana, "Servidor Grafana (Puerto 3000)", cwd=dir_grafana)
            else:
                print("   [INFO] Grafana: No detectado aún en el sistema.")
                print("          (En cuanto descomprimas Grafana en la carpeta, se iniciará solo).")

        # 6. Servidor Web del Menú y Login (Puerto 8000)
        print("\n4. Interfaz de Usuario:")
        httpd = iniciar_servidor_estatico()

        # Esperar 2 segundos para estabilizar y abrir navegador
        time.sleep(2)
        print(f"\n-> Abriendo panel en el navegador: {URL_LOGIN}")
        webbrowser.open(URL_LOGIN)

        print("\n" + "=" * 65)
        print(" ¡TODO CORRIENDO EXITOSAMENTE!")
        print(" Presiona Ctrl + C en esta ventana para apagar todos los servicios.")
        print("=" * 65 + "\n")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nInterrupción detectada por el usuario (Ctrl + C)...")
    finally:
        detener_todo(httpd)


if __name__ == "__main__":
    main()
