import cv2
import numpy as np
import time
import threading
import atexit
import math
import database


from flask import Flask, Response, jsonify, render_template_string, send_from_directory


# Inicializa las tablas al arrancar
database.inicializar_bd()
# ============================================================
# CONFIGURACION
# ============================================================
import json
import os

RUTA_CONFIG_HW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_hardware.json")

# Valores por defecto
FUENTE = "esp32"
URL_ESP32 = "http://192.168.4.1:81/stream"
INDICE_CAMARA = 0

if os.path.exists(RUTA_CONFIG_HW):
    try:
        with open(RUTA_CONFIG_HW, "r", encoding="utf-8") as f:
            datos_cfg = json.load(f)
            cam_cfg = datos_cfg.get("camara_esp32_cam", {})
            FUENTE = cam_cfg.get("fuente", FUENTE)
            ip_cam = cam_cfg.get("ip_esp32_cam", "192.168.4.1")
            puerto_cam = cam_cfg.get("puerto_stream", 81)
            ruta_stream = cam_cfg.get("ruta_stream", "/stream")
            URL_ESP32 = f"http://{ip_cam}:{puerto_cam}{ruta_stream}"
            INDICE_CAMARA = cam_cfg.get("indice_webcam_local", 0)
    except Exception as _e:
        pass
ANCHO_CAMARA = 640
ALTO_CAMARA = 480
FPS_CAMARA = 30

HOST = "0.0.0.0"
PUERTO = 5000

MAX_POLLITOS = 6
AREA_MINIMA = 1500
DISTANCIA_AGRUPAMIENTO = 120
MIN_POLLITOS_GRUPO = 4
TIEMPO_ALERTA = 10
GRACIA_CIERRE = 3

# Cuantos frames fallidos seguidos antes de reconectar con la ESP32-CAM
FALLOS_PARA_RECONECTAR = 30

URL_MENU = "http://localhost:8000/menu.html"

# Seguimiento por centroides y deteccion de movimiento con OpenCV.
# No utiliza YOLO, archivos .pt ni ByteTrack.
app = Flask(__name__)

camera = None
frame_actual = None
frame_lock = threading.Lock()
camara_lock = threading.Lock()
detener_evento = threading.Event()

espectadores = 0
espectadores_lock = threading.Lock()
ultimo_espectador_ts = time.time()

tracking_data = {
    "pollitos": 0,
    "maximo": MAX_POLLITOS,
    "fps": 0,
    "estado": "iniciando",
    "agrupamiento": False,
    "tiempo_agrupamiento": 0,
    "alerta": False,
    "timestamp": 0
}
tracking_data_lock = threading.Lock()

# Estado del seguimiento por centroides
objetos = {}
siguiente_id = 1
back_sub = cv2.createBackgroundSubtractorMOG2(
    history=500, varThreshold=25, detectShadows=True
)
kernel = np.ones((3, 3), np.uint8)


def abrir_camara():
    global camera

    if FUENTE == "esp32":
        print(f"Conectando a la ESP32-CAM: {URL_ESP32} ...")
        nueva = None
        try:
            # Timeouts de 5 s para que no se quede colgado si la camara no responde.
            nueva = cv2.VideoCapture(
                URL_ESP32, cv2.CAP_FFMPEG,
                [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
                 cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000]
            )
        except Exception:
            # OpenCV antiguo sin soporte de parametros en el constructor.
            nueva = cv2.VideoCapture(URL_ESP32)

        if nueva is None or not nueva.isOpened():
            if nueva is not None:
                nueva.release()
            print("[ERROR] No se pudo conectar a la ESP32-CAM. Revisa la red y la IP.")
            return False

        nueva.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # menos retraso en el video
        camera = nueva
        print("[OK] ESP32-CAM conectada.")
        return True

    # ---- Webcam del PC (comportamiento original) ----
    print(f"Abriendo camara {INDICE_CAMARA}...")
    # DirectShow suele funcionar bien en Windows.
    nueva = cv2.VideoCapture(INDICE_CAMARA, cv2.CAP_DSHOW)
    if not nueva.isOpened():
        nueva.release()
        # Intento alternativo para equipos donde DirectShow no este disponible.
        nueva = cv2.VideoCapture(INDICE_CAMARA)
    if not nueva.isOpened():
        nueva.release()
        print("[ERROR] No se pudo abrir la camara.")
        return False

    nueva.set(cv2.CAP_PROP_FRAME_WIDTH, ANCHO_CAMARA)
    nueva.set(cv2.CAP_PROP_FRAME_HEIGHT, ALTO_CAMARA)
    nueva.set(cv2.CAP_PROP_FPS, FPS_CAMARA)
    camera = nueva
    print("[OK] Camara abierta.")
    return True


def cerrar_camara():
    global camera
    with camara_lock:
        if camera is not None:
            try:
                camera.release()
            except Exception as exc:
                print(f"[AVISO] Error al cerrar la camara: {exc}")
            camera = None
            print("[OK] Camara liberada.")


def distancia(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def analizar_agrupamiento(pollitos):
    if len(pollitos) < MIN_POLLITOS_GRUPO:
        return False, 0

    grupo = []
    for p in pollitos:
        vecinos = sum(
            1 for otro in pollitos
            if otro["id"] != p["id"]
            and distancia((p["cx"], p["cy"]), (otro["cx"], otro["cy"]))
            <= DISTANCIA_AGRUPAMIENTO
        )
        if vecinos >= 2:
            grupo.append(p)

    return (True, len(grupo)) if len(grupo) >= MIN_POLLITOS_GRUPO else (False, len(grupo))


def detectar_objetos(frame):
    """Detecta regiones en movimiento; no reconoce la especie del animal."""
    global objetos, siguiente_id, back_sub

    mascara = back_sub.apply(frame)
    _, mascara = cv2.threshold(mascara, 200, 255, cv2.THRESH_BINARY)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, kernel)
    mascara = cv2.dilate(mascara, kernel, iterations=2)

    contornos, _ = cv2.findContours(
        mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    detecciones = []
    for contorno in contornos:
        area = cv2.contourArea(contorno)
        if area < AREA_MINIMA:
            continue
        x, y, w, h = cv2.boundingRect(contorno)
        detecciones.append({
            "x1": x, "y1": y, "x2": x + w, "y2": y + h,
            "cx": x + w // 2, "cy": y + h // 2, "area": area
        })

    # Primero procesa las detecciones mayores, hasta el limite configurado.
    detecciones.sort(key=lambda d: d["area"], reverse=True)
    detecciones = detecciones[:MAX_POLLITOS]

    # Asociacion sencilla por proximidad entre centroides de frames consecutivos.
    no_asignados = set(objetos.keys())
    nuevos_objetos = {}
    pollitos = []

    for det in detecciones:
        mejor_id = None
        mejor_dist = float("inf")
        for oid in list(no_asignados):
            anterior = objetos[oid]
            d = distancia((det["cx"], det["cy"]), (anterior["cx"], anterior["cy"]))
            if d < mejor_dist and d < 80:
                mejor_id, mejor_dist = oid, d

        if mejor_id is None:
            mejor_id = siguiente_id
            siguiente_id += 1
        else:
            no_asignados.discard(mejor_id)

        obj = {**det, "id": mejor_id, "perdido": 0}
        nuevos_objetos[mejor_id] = obj
        pollitos.append(obj)

    # Conserva brevemente objetos no detectados para reducir cambios de ID.
    for oid in no_asignados:
        anterior = objetos[oid]
        anterior["perdido"] = anterior.get("perdido", 0) + 1
        if anterior["perdido"] <= 3:
            nuevos_objetos[oid] = anterior

    objetos = nuevos_objetos
    return pollitos, mascara


def ejecutar_tracking():
    global frame_actual, back_sub, objetos, siguiente_id
    frames = 0
    inicio = time.time()
    inicio_agrupamiento = None
    ultimo_guardado_db = 0
    fallos = 0
    print("[INFO] Seguimiento OpenCV iniciado.")

    while not detener_evento.is_set():
        with camara_lock:
            cam = camera
            if cam is None:
                ok, frame = False, None
            else:
                ok, frame = cam.read()

        if cam is None:
            # Si hay alguien viendo el video y la camara se cayo, reintenta.
            with espectadores_lock:
                hay_espectadores = espectadores > 0
            if hay_espectadores:
                asegurar_camara()
            time.sleep(0.5)
            continue

        if not ok or frame is None:
            fallos += 1
            if fallos >= FALLOS_PARA_RECONECTAR:
                print("[AVISO] Se perdio el video, reconectando...")
                cerrar_camara()
                with frame_lock:
                    frame_actual = None
                with tracking_data_lock:
                    tracking_data["estado"] = "reconectando"
                fallos = 0
            time.sleep(0.05)
            continue
        fallos = 0

        # La ESP32-CAM puede enviar otra resolucion (por ejemplo 320x240).
        # Se ajusta para que AREA_MINIMA y las distancias sigan funcionando.
        if frame.shape[1] != ANCHO_CAMARA or frame.shape[0] != ALTO_CAMARA:
            frame = cv2.resize(frame, (ANCHO_CAMARA, ALTO_CAMARA))

        try:
            pollitos, _ = detectar_objetos(frame)
            salida = frame.copy()
            agrupamiento, cantidad_grupo = analizar_agrupamiento(pollitos)

            ahora = time.time()
            if agrupamiento:
                if inicio_agrupamiento is None:
                    inicio_agrupamiento = ahora
                tiempo_agrupamiento = ahora - inicio_agrupamiento
            else:
                inicio_agrupamiento = None
                tiempo_agrupamiento = 0

            alerta = agrupamiento and tiempo_agrupamiento >= TIEMPO_ALERTA

            for p in pollitos:
                x1, y1, x2, y2 = p["x1"], p["y1"], p["x2"], p["y2"]
                color = (0, 0, 255) if alerta else (0, 255, 0)
                cv2.rectangle(salida, (x1, y1), (x2, y2), color, 2)
                cv2.circle(salida, (p["cx"], p["cy"]), 4, (255, 0, 0), -1)
                cv2.putText(
                    salida, f"OBJETO ID:{p['id']}",
                    (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2
                )

            frames += 1
            elapsed = time.time() - inicio
            fps = frames / elapsed if elapsed > 0 else 0

            cv2.rectangle(salida, (0, 0), (520, 115), (0, 0, 0), -1)
            cv2.putText(salida, f"OBJETOS: {len(pollitos)}/{MAX_POLLITOS}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(salida, f"FPS: {fps:.1f}",
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

            if alerta:
                estado_texto, color_estado = "ALERTA: GRUPO DETECTADO", (0, 0, 255)
            elif agrupamiento:
                estado_texto, color_estado = f"AGRUPAMIENTO: {cantidad_grupo}", (0, 165, 255)
            else:
                estado_texto, color_estado = "ESTADO: NORMAL", (0, 255, 0)
            cv2.putText(salida, estado_texto, (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color_estado, 2)

            with frame_lock:
                frame_actual = salida.copy()
            with tracking_data_lock:
                tracking_data.update({
                    "pollitos": len(pollitos),
                    "fps": round(fps, 2),
                    "estado": "alerta" if alerta else ("agrupamiento" if agrupamiento else "seguimiento activo"),
                    "agrupamiento": agrupamiento,
                    "tiempo_agrupamiento": round(tiempo_agrupamiento, 1),
                    "alerta": alerta,
                    "timestamp": time.time()
                })

            # Guardado periódico en SQLite (cada 3 segundos)
            if ahora - ultimo_guardado_db >= 3.0:
                ultimo_guardado_db = ahora
                try:
                    database.guardar_resumen(
                        pollitos=len(pollitos),
                        fps=fps,
                        agrupamiento=agrupamiento,
                        tiempo_agrupados=tiempo_agrupamiento,
                        alerta=alerta
                    )
                except Exception:
                    pass
        except Exception as exc:
            print(f"[ERROR] Seguimiento OpenCV: {exc}")
            time.sleep(0.1)

    print("[INFO] Hilo de seguimiento detenido.")


def asegurar_camara():
    global back_sub, objetos, siguiente_id
    if camera is not None:
        return True
    with camara_lock:
        if camera is not None:
            return True
        ok = abrir_camara()
        if ok:
            # Reinicia el sustractor cuando la camara se vuelve a abrir.
            back_sub = cv2.createBackgroundSubtractorMOG2(
                history=500, varThreshold=25, detectShadows=True
            )
            objetos = {}
            siguiente_id = 1
        else:
            with tracking_data_lock:
                tracking_data["estado"] = "sin cámara"
        return ok


def cuadro_aviso(texto):
    img = np.zeros((ALTO_CAMARA, ANCHO_CAMARA, 3), dtype=np.uint8)
    cv2.putText(img, texto, (15, ALTO_CAMARA // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 165, 255), 2)
    return img


def espectador_entra():
    global espectadores
    with espectadores_lock:
        espectadores += 1
    return asegurar_camara()


def espectador_sale():
    global espectadores, ultimo_espectador_ts
    with espectadores_lock:
        espectadores = max(0, espectadores - 1)
        ultimo_espectador_ts = time.time()


def generar_video():
    camara_ok = espectador_entra()
    ultimo_intento = time.time()
    try:
        while not detener_evento.is_set():
            if not camara_ok and time.time() - ultimo_intento >= 2:
                camara_ok = asegurar_camara()
                ultimo_intento = time.time()

            if not camara_ok:
                if FUENTE == "esp32":
                    frame = cuadro_aviso("SIN ESP32-CAM: revisa la red WiFi y la IP")
                else:
                    frame = cuadro_aviso("SIN CAMARA: revisa que este conectada")
                time.sleep(0.2)
            else:
                with frame_lock:
                    frame = None if frame_actual is None else frame_actual.copy()
                if frame is None:
                    time.sleep(0.05)
                    continue

            ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ret:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                       + buffer.tobytes() + b"\r\n")
    finally:
        espectador_sale()


def vigilar_espectadores():
    global frame_actual
    while not detener_evento.is_set():
        time.sleep(1)
        with espectadores_lock:
            nadie = espectadores == 0
            sin_ver = time.time() - ultimo_espectador_ts
        if nadie and camera is not None and sin_ver >= GRACIA_CIERRE:
            cerrar_camara()
            with frame_lock:
                frame_actual = None
            with tracking_data_lock:
                tracking_data.update({
                    "pollitos": 0, "fps": 0, "estado": "en pausa",
                    "agrupamiento": False, "tiempo_agrupamiento": 0, "alerta": False
                })


HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Seguimiento de pollitos</title>
<style>
body{margin:0;background:#111;color:white;font-family:Arial,sans-serif}
header{background:#222;padding:18px;text-align:center}
.container{width:95%;max-width:1200px;margin:auto}
.video{margin-top:20px;background:#000;border-radius:12px;overflow:hidden}
.video img{width:100%;display:block}
.cards{display:flex;flex-wrap:wrap;gap:15px;margin:20px 0}
.card{background:#222;padding:20px;border-radius:12px;flex:1;min-width:160px}
.valor{font-size:26px;font-weight:bold}
.normal{color:#00ff66}.alerta{color:#ff3333}.warning{color:orange}
a{color:#bbb;text-decoration:none}
.note{color:#bbb;font-size:13px}
</style>
</head>
<body>
<header>
<a href="__URL_MENU__">&larr; Volver al menú</a>
<h1>🐔 Seguimiento de pollitos</h1>
<p>OpenCV: detección de movimiento y seguimiento por proximidad</p>
</header>
<div class="container">
<div class="video"><img src="/video_feed" alt="Video de seguimiento"></div>
<p class="note">La detección se basa en movimiento; puede contar objetos incorrectamente si se solapan o si cambia la iluminación.</p>
<div class="cards">
<div class="card"><h3>Objetos detectados</h3><div class="valor" id="pollitos">0/6</div></div>
<div class="card"><h3>FPS</h3><div class="valor" id="fps">0</div></div>
<div class="card"><h3>Estado</h3><div class="valor normal" id="estado">Iniciando</div></div>
<div class="card"><h3>Agrupamiento</h3><div class="valor" id="agrupamiento">No</div></div>
<div class="card"><h3>Tiempo agrupados</h3><div class="valor" id="tiempo">0 s</div></div>
</div>
</div>
<script>
async function actualizarDatos(){
 try{
  const respuesta=await fetch("/tracking_data");
  const datos=await respuesta.json();
  document.getElementById("pollitos").textContent=datos.pollitos+"/"+datos.maximo;
  document.getElementById("fps").textContent=datos.fps;
  const estado=document.getElementById("estado");
  estado.textContent=datos.estado;
  estado.className="valor "+(datos.alerta?"alerta":datos.agrupamiento?"warning":"normal");
  document.getElementById("agrupamiento").textContent=datos.agrupamiento?"SÍ":"NO";
  document.getElementById("tiempo").textContent=datos.tiempo_agrupamiento+" s";
 }catch(e){console.error(e);}
}
setInterval(actualizarDatos,1000); actualizarDatos();
</script>
</body>
</html>
"""


@app.route("/")
def inicio():
    ruta_tracking = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tracking.html")
    if os.path.exists(ruta_tracking):
        return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "tracking.html")
    return render_template_string(HTML.replace("__URL_MENU__", URL_MENU))


@app.route("/styles.css")
def estilos():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "styles.css")


@app.route("/chatbot_widget.js")
def chatbot_widget():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "chatbot_widget.js")


@app.route("/api/chatbot", methods=["GET", "POST", "OPTIONS"])
def api_chatbot():
    import chatbot
    from flask import request
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    msg = ""
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        msg = data.get("mensaje", "")
    else:
        msg = request.args.get("mensaje", "")
    return jsonify({"ok": True, "resultado": chatbot.responder_consulta(msg)})


@app.route("/video_feed")
def video_feed():
    return Response(generar_video(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/tracking_data")
def obtener_datos():
    with tracking_data_lock:
        return jsonify(tracking_data.copy())


@app.route("/metrics")
def metrics():
    with tracking_data_lock:
        datos = tracking_data.copy()
    texto = (
        f"pollitos_detectados {datos['pollitos']}\n"
        f"pollitos_maximos {MAX_POLLITOS}\n"
        f"fps_tracking {datos['fps']}\n"
        f"alerta_agrupamiento {1 if datos['alerta'] else 0}\n"
    )
    return Response(texto, mimetype="text/plain")


@app.route("/reiniciar", methods=["GET", "POST"])
def reiniciar():
    global back_sub, objetos, siguiente_id, frame_actual
    back_sub = cv2.createBackgroundSubtractorMOG2(
        history=500, varThreshold=25, detectShadows=True
    )
    objetos = {}
    siguiente_id = 1
    with frame_lock:
        frame_actual = None
    with tracking_data_lock:
        tracking_data.update({
            "pollitos": 0, "estado": "reiniciando", "agrupamiento": False,
            "tiempo_agrupamiento": 0, "alerta": False
        })
    return jsonify({"ok": True, "mensaje": "Sistema reiniciado"})


def detener():
    if not detener_evento.is_set():
        detener_evento.set()
    cerrar_camara()
    print("[OK] Sistema cerrado correctamente.")


atexit.register(detener)


def main():
    print("=" * 55)
    print("SEGUIMIENTO DE POLLITOS CON OPENCV")
    if FUENTE == "esp32":
        print(f"Fuente: ESP32-CAM ({URL_ESP32}) | Maximo objetos: {MAX_POLLITOS}")
    else:
        print(f"Fuente: webcam {INDICE_CAMARA} | Maximo objetos: {MAX_POLLITOS}")
    print(f"Dashboard: http://127.0.0.1:{PUERTO}")
    print("Presiona CTRL+C para detener.")
    print("=" * 55)

    hilo_tracking = threading.Thread(target=ejecutar_tracking, daemon=True)
    hilo_tracking.start()
    threading.Thread(target=vigilar_espectadores, daemon=True).start()
    try:
        app.run(host=HOST, port=PUERTO, debug=False,
                threaded=True, use_reloader=False)
    except KeyboardInterrupt:
        print("[INFO] CTRL+C detectado.")
    finally:
        detener()
        hilo_tracking.join(timeout=5)


if __name__ == "__main__":
    main()