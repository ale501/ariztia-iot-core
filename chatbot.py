"""
MOTOR DEL CHATBOT ASISTENTE VIRTUAL — ARIZTÍA IoT
=================================================
Procesa consultas en lenguaje natural con soporte dual:
  1. Inteligencia Artificial avanzada vía OpenRouter (Modelos gratuitos: LLaMA 3.3, Gemini 2.0, DeepSeek R1)
  2. Motor de respaldo local determinista y sin dependencias externas
"""

import json
import os
import re
import time
import requests
import mensajeria

CARPETA = os.path.dirname(os.path.abspath(__file__))


def cargar_config_openrouter():
    """Carga configuración de OpenRouter desde config_hardware.json."""
    ruta_cfg = os.path.join(CARPETA, "config_hardware.json")
    if os.path.exists(ruta_cfg):
        try:
            with open(ruta_cfg, "r", encoding="utf-8") as f:
                d = json.load(f)
                return d.get("ia_openrouter", {})
        except Exception:
            pass
    return {}


def consultar_estado_ambiental():
    """Consulta los datos en vivo del backend de Ariztía (puerto 5001)."""
    try:
        resp = requests.get("http://127.0.0.1:5001/ariztia_data", timeout=1.5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def consultar_estado_tracking():
    """Consulta los datos en vivo del servicio de visión (puerto 5000)."""
    try:
        resp = requests.get("http://127.0.0.1:5000/tracking_data", timeout=1.5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def consultar_openrouter(pregunta, datos_amb, datos_trk):
    """
    Envía la consulta a OpenRouter.ai con el contexto en tiempo real del galpón inyectado.
    Soporta modelos 100% gratuitos (Gemini 2.0 Flash Free, DeepSeek R1 Free, LLaMA 3.3 Free).
    """
    cfg = cargar_config_openrouter()
    if not cfg.get("habilitado", False):
        return None

    api_key = cfg.get("api_key", "").strip()
    if not api_key or "PEGA_AQUI" in api_key:
        return None

    modelo = cfg.get("modelo", "google/gemini-2.0-flash-exp:free")

    # Inyección de datos vivos en el prompt de sistema
    t_str = "23.5 °C"
    h_str = "55.0 %"
    iec_str = "78.5"
    nivel_str = "Confort Normal"
    if datos_amb and datos_amb.get("actual"):
        act = datos_amb["actual"]
        t_str = f"{act.get('temperatura', 'N/A')} °C"
        h_str = f"{act.get('humedad', 'N/A')} %"
        iec_str = f"{act.get('iec', 'N/A')}"
        nivel_str = act.get("etiqueta", "Confort")

    pollos_str = "0 aves"
    fps_str = "30 FPS"
    alerta_pollos = "Normal, aves dispersas"
    if datos_trk:
        pollos_str = f"{datos_trk.get('pollitos', 0)} / {datos_trk.get('maximo', 6)} pollos detectados"
        fps_str = f"{datos_trk.get('fps', 0):.1f} FPS"
        if datos_trk.get("alerta"):
            alerta_pollos = "¡ALERTA CRÍTICA DE AMONTONAMIENTO ACTIVA (>10s)!"
        elif datos_trk.get("agrupamiento"):
            alerta_pollos = "Agrupamiento de aves en curso"

    system_prompt = f"""Eres el Asistente Experto en Inteligencia Artificial y Bienestar Avícola para galpones de Ariztía (Chile).
Tu misión es asesorar a los operadores del galpón, veterinarios y administradores con base técnica sólida, concisa y empática.

DATOS DEL GALPÓN EN VIVO EN ESTE INSTANTE:
- Temperatura ambiente: {t_str}
- Humedad Relativa: {h_str}
- Índice de Estrés Calórico (IEC = T°C + HR%): {iec_str} (Nivel: {nivel_str})
- Conteo de aves en cámara (OpenCV): {pollos_str} (a {fps_str})
- Estado de comportamiento / agrupamiento: {alerta_pollos}

ESCALA DE CONTROL ARIZTÍA (IEC):
- IEC < 95: Confort óptimo.
- IEC 95 - 104: Precaución térmica. Encendido preventivo de ventiladores.
- IEC 105 - 110: Estrés calórico. Notificación obligatoria, nebulización forzada.
- IEC > 110: Crítico / Sofocamiento inminente. Protocolo de emergencia.

Instrucciones:
1. Responde de forma clara, directa, profesional y amable en español.
2. Utiliza los datos del galpón en vivo siempre que sea pertinente.
3. Puedes usar emojis técnicos y formato markdown (*negritas*, listas).
4. Mantén las respuestas en un tamaño adecuado para un chat (2-4 párrafos máximo).
"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Ariztia IoT Core",
        "Content-Type": "application/json"
    }

    payload = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": pregunta}
        ],
        "temperature": 0.4,
        "max_tokens": 600
    }

    try:
        resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=12)
        if resp.status_code == 200:
            res_json = resp.json()
            eleccion = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")
            if eleccion:
                return eleccion
        else:
            print(f"[OpenRouter Error {resp.status_code}] {resp.text}")
    except Exception as e:
        print(f"[OpenRouter Conexión] {e}")

    return None


def responder_consulta(mensaje_usuario):
    """
    Motor de procesamiento:
    1. Si es un comando de acción (WhatsApp, Webex, reportes) -> lo ejecuta directo.
    2. Si OpenRouter está activo -> responde con LLM avanzado + contexto en vivo.
    3. Si no hay internet o clave -> fallback al motor determinista local.
    """
    msg = (mensaje_usuario or "").lower().strip()

    if not msg:
        return {
            "respuesta": "¡Hola! Soy el asistente virtual de **Ariztía IoT** 🐔 con soporte de IA. Puedo analizar el bienestar del galpón, temperatura, estrés calórico o enviar alertas a WhatsApp y Webex. ¿Qué deseas consultar?",
            "sugerencias": ["Estado general", "Temperatura e IEC", "Tracking de pollos", "Enviar reporte a Webex"]
        }

    # Acción de envío manual por mensajería
    if re.search(r"(whatsapp|wsp|telegram|webex|mensaje|notifica|reporte)", msg):
        datos_amb = consultar_estado_ambiental()
        t = datos_amb["actual"]["temperatura"] if (datos_amb and datos_amb.get("actual")) else 24.5
        h = datos_amb["actual"]["humedad"] if (datos_amb and datos_amb.get("actual")) else 55.0
        iec = datos_amb["actual"]["iec"] if (datos_amb and datos_amb.get("actual")) else 79.5

        detalle = f"Reporte manual solicitado desde el Chatbot: T={t}°C, HR={h}%, IEC={iec}."
        res = mensajeria.enviar_alerta_multicanal("Reporte de Telemetría", detalle, nivel="info", forzar=True)

        return {
            "respuesta": (
                "📲 **Disparo de mensajería ejecutado.**\n"
                "Se ha enviado la notificación con la telemetría actual a tus canales activos (Cisco Webex / WhatsApp / Telegram).\n\n"
                "*(Revisa tu espacio de Webex o tu chat)*."
            ),
            "sugerencias": ["Estado ambiental", "Tracking de pollos", "Alertas activas"]
        }

    # Obtener telemetría fresca
    datos_amb = consultar_estado_ambiental()
    datos_trk = consultar_estado_tracking()

    # 1. Intentar responder con OpenRouter (IA avanzada con razonamiento)
    respuesta_ia = consultar_openrouter(mensaje_usuario, datos_amb, datos_trk)
    if respuesta_ia:
        return {
            "respuesta": respuesta_ia,
            "origen": "openrouter_ia",
            "sugerencias": ["¿Cómo optimizar el galpón?", "Enviar reporte a Webex", "Ver alertas"]
        }

    # 2. Motor de Respuestas Local (Fallback determinista garantizado)
    # Saludos
    if re.search(r"\b(hola|buenos|buenas|saludos|hey|alo)\b", msg):
        return {
            "respuesta": "¡Hola! 👋 Estoy monitoreando en tiempo real los galpones de Ariztía. ¿Deseas consultar el **ambiente**, la **cámara de pollos** o las **alertas**?",
            "sugerencias": ["¿Cómo están las condiciones?", "¿Hay alguna alerta?", "Ver cámara de pollitos"]
        }

    # Consulta de Temperatura / Humedad / IEC
    if re.search(r"(temp|clima|humedad|iec|calor|frio|ambiente|grado)", msg):
        if not datos_amb or not datos_amb.get("actual"):
            return {"respuesta": "⚠️ El servicio ambiental (`app_ariztia.py` :5001) aún no tiene lecturas o está iniciando."}

        act = datos_amb["actual"]
        t = act.get("temperatura", "N/A")
        h = act.get("humedad", "N/A")
        iec = act.get("iec", "N/A")
        nivel = act.get("nivel", "confort")
        etiqueta = act.get("etiqueta", "Normal")
        accion = act.get("accion", "Registro normal")
        icono = "🟢" if nivel == "confort" else "🟡" if nivel == "precaucion" else "🔴"

        resp_texto = (
            f"🌡️ **Telemetría Ambiental en Galpón:**\n"
            f"• **Temperatura:** `{t} °C`\n"
            f"• **Humedad Relativa:** `{h} %`\n"
            f"• **Índice de Estrés Calórico (IEC):** `{iec}` ({icono} {etiqueta})\n"
            f"• **Protocolo recomendado:** {accion}\n"
            f"• **Hora:** {act.get('fecha_hora', '--')}"
        )
        return {
            "respuesta": resp_texto,
            "sugerencias": ["¿Qué significa el IEC?", "¿Hay alertas activas?", "Estado de los pollos"]
        }

    # Consulta de Tracking
    if re.search(r"(pollo|pollito|camara|video|agrup|vision|conteo|cuanto|fps)", msg):
        if not datos_trk:
            return {"respuesta": "📷 El servicio de visión (`prueba.py` :5000) no responde en este momento."}

        pollos = datos_trk.get("pollitos", 0)
        maximo = datos_trk.get("maximo", 6)
        fps = datos_trk.get("fps", 0)
        agrup = datos_trk.get("agrupamiento", False)
        tiempo_agrup = datos_trk.get("tiempo_agrupamiento", 0)
        alerta = datos_trk.get("alerta", False)

        if alerta:
            estado_txt = f"🚨 **¡ALERTA CRÍTICA DE AMONTONAMIENTO!** Pollos concentrados por más de {tiempo_agrup}s."
        elif agrup:
            estado_txt = f"⚠️ **Agrupamiento en curso:** {tiempo_agrup}s acumulados."
        else:
            estado_txt = "✅ **Comportamiento normal:** Aves dispersas por el galpón."

        resp_texto = (
            f"🐣 **Monitoreo de Aves por Visión Artificial:**\n"
            f"• **Pollos detectados en cuadro:** `{pollos} / {maximo}`\n"
            f"• **Rendimiento:** `{fps:.1f} FPS`\n"
            f"• **Estado:** {estado_txt}\n"
            f"• **Visor en vivo:** [Abrir Video Feed](http://localhost:5000)"
        )
        return {
            "respuesta": resp_texto,
            "sugerencias": ["Estado ambiental", "Enviar reporte a Webex", "Alertas activas"]
        }

    # Consulta de Alertas
    if re.search(r"(alerta|alarma|peligro|critico|urgente|problema)", msg):
        alertas = []
        if datos_amb and datos_amb.get("actual"):
            a = datos_amb["actual"]
            if a.get("nivel") in ["estres", "critico"]:
                alertas.append(f"🔥 **Estrés Calórico {a.get('etiqueta')}:** {a.get('temperatura')}°C + {a.get('humedad')}% (IEC: {a.get('iec')})")
            if a.get("estado_conexion") == "Desconectado":
                alertas.append("🔌 **Sensor Desconectado:** Pérdida de comunicación con el ESP32.")

        if datos_trk and datos_trk.get("alerta"):
            alertas.append("🚨 **Amontonamiento de Pollos:** Aves amontonadas por más de 10 segundos.")

        if not alertas:
            return {
                "respuesta": "✅ **Todo en orden:** No hay alertas activas en los galpones. Las aves y el clima están en rangos óptimos.",
                "sugerencias": ["Temperatura actual", "Ver estado de pollitos"]
            }

        return {
            "respuesta": "⚠️ **Alertas activas en este momento:**\n" + "\n".join([f"• {item}" for item in alertas]),
            "sugerencias": ["Enviar reporte a Webex", "¿Qué acciones tomar?"]
        }

    # Explicación IEC
    if re.search(r"(que es iec|escala|formula|norma|umbral)", msg):
        return {
            "respuesta": (
                "📖 **Índice de Estrés Calórico (IEC) en Ariztía:**\n"
                "• **Fórmula:** `IEC = Temperatura (°C) + Humedad Relativa (%)`\n\n"
                "**Tabla de Control Operativo:**\n"
                "• 🟢 **< 95 (Confort):** Registro estándar sin intervención.\n"
                "• 🟡 **95 – 104 (Precaución):** Alerta preventiva; encender ventiladores y extractores.\n"
                "• 🟠 **105 – 110 (Estrés Calórico):** Notificación obligatoria con acuse de recibo; nebulización.\n"
                "• 🔴 **> 110 (Crítico):** Sofocamiento inminente de las aves; protocolo de emergencia y enfriamiento forzado."
            ),
            "sugerencias": ["Ver temperatura actual", "Ver alertas"]
        }

    # Respuesta genérica
    return {
        "respuesta": (
            f"He recibido tu consulta: *\"{mensaje_usuario}\"*.\n"
            "Puedo ayudarte con la telemetría en tiempo real de los galpones. Puedes preguntarme:\n"
            "• *\"¿Cuál es la temperatura y humedad?\"*\n"
            "• *\"¿Hay pollos amontonados?\"*\n"
            "• *\"Enviar reporte a Webex\"*\n"
            "• *\"¿Qué acciones tomar si sube el calor?\"*"
        ),
        "sugerencias": ["Estado general", "Temperatura actual", "Alertas activas", "Enviar reporte a Webex"]
    }
