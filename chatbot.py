"""
MOTOR DEL CHATBOT ASISTENTE VIRTUAL — ARIZTÍA IoT
=================================================
Procesa consultas en lenguaje natural y responde con datos en tiempo real:
  - Temperatura, Humedad e Índice de Estrés Calórico (IEC)
  - Estado del tracking de pollos (conteo, amontonamiento)
  - Alertas activas y recomendaciones técnicas avícolas
  - Disparo de reportes hacia WhatsApp, Telegram o Webex
"""

import json
import os
import re
import time
import requests
import mensajeria

CARPETA = os.path.dirname(os.path.abspath(__file__))


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


def responder_consulta(mensaje_usuario):
    """
    Motor de procesamiento de intenciones y lenguaje natural para el galpón.
    Devuelve: {"respuesta": str, "accion": str, "datos": dict}
    """
    msg = (mensaje_usuario or "").lower().strip()

    if not msg:
      return {
          "respuesta": (
              "¡Hola! Soy el asistente virtual de **Ariztía IoT** 🐔. "
              "Puedo informarte sobre la temperatura del galpón, el estrés"
              " calórico (IEC), el conteo de aves o enviar alertas a tu"
              " WhatsApp. ¿En qué te ayudo?"
          ),
          "sugerencias": [
              "Estado general",
              "Temperatura e IEC",
              "Tracking de pollos",
              "Enviar reporte WhatsApp",
          ],
      }

    # 1. Saludos
    if re.search(r"\b(hola|buenos|buenas|saludos|hey|alo)\b", msg):
      return {
          "respuesta": (
              "¡Hola! 👋 Estoy monitoreando en tiempo real los galpones de"
              " Ariztía. ¿Deseas consultar el **ambiente**, la **cámara de"
              " pollos** o las **alertas**?"
          ),
          "sugerencias": [
              "¿Cómo están las condiciones?",
              "¿Hay alguna alerta?",
              "Ver cámara de pollitos",
          ],
      }

    # 2. Consulta de Temperatura / Humedad / IEC
    if re.search(r"(temp|clima|humedad|iec|calor|frio|ambiente|grado)", msg):
      datos = consultar_estado_ambiental()
      if not datos or not datos.get("actual"):
        return {
            "respuesta": (
                "⚠️ El servicio ambiental (`app_ariztia.py` :5001) aún no tiene"
                " lecturas registradas o está iniciando. Por favor verifica que"
                " el backend esté corriendo."
            )
        }

      act = datos["actual"]
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
          f"• **Hora de muestra:** {act.get('fecha_hora', '--')}"
      )
      return {
          "respuesta": resp_texto,
          "sugerencias": [
              "¿Qué significa el IEC?",
              "¿Hay alertas activas?",
              "Estado de los pollos",
          ],
      }

    # 3. Consulta de Tracking de Pollos / Cámara / Agrupamiento
    if re.search(
        r"(pollo|pollito|camara|video|agrup|vision|conteo|cuanto|fps)", msg
    ):
      datos_track = consultar_estado_tracking()
      if not datos_track:
        return {
            "respuesta": (
                "📷 El servicio de visión (`prueba.py` :5000) no responde en"
                " este momento. Asegúrate de que esté iniciado con"
                " `iniciar.py`."
            )
        }

      pollos = datos_track.get("pollitos", 0)
      maximo = datos_track.get("maximo", 6)
      fps = datos_track.get("fps", 0)
      agrup = datos_track.get("agrupamiento", False)
      tiempo_agrup = datos_track.get("tiempo_agrupamiento", 0)
      alerta = datos_track.get("alerta", False)

      if alerta:
        estado_txt = (
            "🚨 **¡ALERTA CRÍTICA DE AMONTONAMIENTO!** Los pollitos llevan más"
            f" de {tiempo_agrup}s concentrados. Posible foco de frío o falla de"
            " ventilación."
        )
      elif agrup:
        estado_txt = (
            f"⚠️ **Agrupamiento en curso:** Llevan {tiempo_agrup}s acumulados"
            " (cronómetro activo hacia 10s)."
        )
      else:
        estado_txt = (
            "✅ **Comportamiento normal:** Aves dispersas por el galpón."
        )

      resp_texto = (
          f"🐣 **Monitoreo de Aves por Visión Artificial:**\n"
          f"• **Pollos detectados en cuadro:** `{pollos} / {maximo}`\n"
          f"• **Rendimiento de cámara:** `{fps:.1f} FPS`\n"
          f"• **Estado de comportamiento:** {estado_txt}\n"
          f"• **Visor en vivo:** [Abrir Video Feed](http://localhost:5000)"
      )
      return {
          "respuesta": resp_texto,
          "sugerencias": [
              "Estado ambiental",
              "Enviar alerta a WhatsApp",
              "¿Cómo funciona el tracking?",
          ],
      }

    # 4. Consulta de Alertas Generales
    if re.search(r"(alerta|alarma|peligro|critico|urgente|problema)", msg):
      datos_amb = consultar_estado_ambiental()
      datos_trk = consultar_estado_tracking()

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
            "respuesta": "✅ **Todo en orden:** No hay alertas activas en los galpones. Tanto el ambiente como el comportamiento de las aves están en rangos óptimos.",
            "sugerencias": ["Temperatura actual", "Ver estado de pollitos"]
        }

      return {
          "respuesta": "⚠️ **Alertas activas en este momento:**\n" + "\n".join([f"• {item}" for item in alertas]),
          "sugerencias": ["Enviar reporte a WhatsApp", "Enviar a Telegram", "¿Qué acciones tomar?"]
      }

    # 5. Envío manual de mensaje de prueba por WhatsApp / Telegram / Webex
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
              "Se ha enviado la notificación a los canales configurados (WhatsApp / Telegram / Webex).\n\n"
              "*(Para ajustar tu número de WhatsApp o tokens, edita la sección `notificaciones` en `config_hardware.json`)*."
          ),
          "sugerencias": ["Estado ambiental", "¿Cómo configurar mi WhatsApp?"]
      }

    # 6. Explicación de Normativa Ariztía (IEC)
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

    # 7. Respuesta genérica inteligente
    return {
        "respuesta": (
            f"He recibido tu consulta: *\"{mensaje_usuario}\"*.\n"
            "Puedo ayudarte con la telemetría en tiempo real de los galpones. Puedes preguntarme:\n"
            "• *\"¿Cuál es la temperatura y humedad?\"*\n"
            "• *\"¿Hay pollos amontonados?\"*\n"
            "• *\"¿Hay alguna alerta activa?\"*\n"
            "• *\"Enviar reporte a mi WhatsApp\"*"
        ),
        "sugerencias": ["Estado general", "Temperatura actual", "Alertas activas"]
    }
