"""
MÓDULO DE MENSAJERÍA Y NOTIFICACIONES GRATUITAS
================================================
Soporta:
  1. WhatsApp (vía CallMeBot API - 100% Gratuito)
  2. Telegram Bot API (100% Gratuito y sin límites)
  3. Cisco Webex Teams (Incoming Webhooks - 100% Gratuito)
"""

import json
import os
import threading
import time
import requests

CARPETA = os.path.dirname(os.path.abspath(__file__))
RUTA_CONFIG = os.path.join(CARPETA, "config_hardware.json")

# Control de spam para alertas (mínimo 3 minutos entre alertas idénticas)
_ULTIMA_ALERTA_TS = {}
_LOCK_ALERTA = threading.Lock()


def cargar_config_mensajeria():
    """Carga la configuración de notificaciones desde config_hardware.json."""
    cfg_default = {
        "whatsapp": {
            "habilitado": False,
            "numero_telefono": "+56912345678",  # Con código de país (+569...)
            "apikey": ""                        # API Key gratuita de CallMeBot
        },
        "telegram": {
            "habilitado": False,
            "bot_token": "9065892213:AAHzho6Et8QEF3Zxqc0ZpLGLcNsaQPKkW-k",
            "chat_id": ""
        },
        "webex": {
            "habilitado": False,
            "webhook_url": ""                   # Webhook URL de Cisco Webex
        }
    }

    if os.path.exists(RUTA_CONFIG):
        try:
            with open(RUTA_CONFIG, "r", encoding="utf-8") as f:
                datos = json.load(f)
                return datos.get("notificaciones", cfg_default)
        except Exception:
            pass

    return cfg_default


def enviar_whatsapp(mensaje, numero=None, apikey=None):
    """
    Envía mensaje por WhatsApp usando CallMeBot API (Gratuito).
    Para obtener tu apikey gratis:
      1. Agrega a tus contactos de WhatsApp a: +34 644 44 24 33
      2. Envíale un mensaje que diga: "I allow callmebot to send me messages"
      3. El bot te responderá en 10 segundos con tu apikey gratuita.
    """
    cfg = cargar_config_mensajeria().get("whatsapp", {})
    num = numero or cfg.get("numero_telefono")
    key = apikey or cfg.get("apikey")

    if not num or not key:
        return False, "Falta configurar número de teléfono o apikey de CallMeBot"

    # Limpiar formato de teléfono (solo números y signo +)
    num = num.replace(" ", "").replace("-", "")
    if not num.startswith("+"):
        num = "+" + num

    url = f"https://api.callmebot.com/whatsapp.php"
    params = {
        "phone": num,
        "text": mensaje,
        "apikey": key
    }

    try:
        resp = requests.get(url, params=params, timeout=8)
        if resp.status_code == 200:
            return True, "Mensaje de WhatsApp enviado correctamente"
        return False, f"Respuesta de WhatsApp API: {resp.status_code} - {resp.text}"
    except Exception as e:
        return False, f"Error conectando a WhatsApp API: {e}"


def enviar_telegram(mensaje, token=None, chat_id=None):
    """
    Envía mensaje por Telegram Bot API (Gratuito).
    """
    cfg = cargar_config_mensajeria().get("telegram", {})
    bot_token = token or cfg.get("bot_token")
    cid = chat_id or cfg.get("chat_id")

    if not bot_token or not cid:
        return False, "Falta configurar bot_token o chat_id de Telegram"

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": cid,
        "text": mensaje,
        "parse_mode": "Markdown"
    }

    try:
        resp = requests.post(url, json=payload, timeout=8)
        if resp.status_code == 200:
            return True, "Mensaje de Telegram enviado con éxito"
        return False, f"Telegram API error: {resp.text}"
    except Exception as e:
        return False, f"Error conectando a Telegram: {e}"


def enviar_webex(mensaje, webhook_url=None):
    """
    Envía mensaje a un espacio de Cisco Webex Teams usando Incoming Webhook (Gratuito).
    Para crearlo: Ve a Webex App Hub o developer.webex.com -> Webhooks -> Add Incoming Webhook.
    """
    cfg = cargar_config_mensajeria().get("webex", {})
    url = webhook_url or cfg.get("webhook_url")

    if not url:
        return False, "Falta configurar webhook_url de Cisco Webex"

    payload = {
        "markdown": mensaje
    }

    try:
        resp = requests.post(url, json=payload, timeout=8)
        if resp.status_code in [200, 204]:
            return True, "Mensaje de Cisco Webex enviado con éxito"
        return False, f"Webex error: {resp.status_code} - {resp.text}"
    except Exception as e:
        return False, f"Error conectando a Webex: {e}"


def enviar_alerta_multicanal(titulo, detalle, nivel="critico", forzar=False):
    """
    Envía una notificación a todos los canales habilitados en config_hardware.json.
    Aplica protección anti-spam para no inundar el chat.
    """
    global _ULTIMA_ALERTA_TS

    clave_alerta = f"{titulo}_{nivel}"
    ahora = time.time()

    with _LOCK_ALERTA:
        if not forzar and clave_alerta in _ULTIMA_ALERTA_TS:
            hace = ahora - _ULTIMA_ALERTA_TS[clave_alerta]
            if hace < 180:  # Espera mínima de 3 minutos para la misma alerta
                return {"enviado": False, "motivo": f"Silenciada por anti-spam ({int(180 - hace)}s restantes)"}

        _ULTIMA_ALERTA_TS[clave_alerta] = ahora

    icono = "🚨" if nivel == "critico" else "⚠️" if nivel == "precaucion" else "ℹ️"
    mensaje_texto = (
        f"{icono} *ALERTA ARIZTÍA IoT*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"*Evento:* {titulo}\n"
        f"*Nivel:* {nivel.upper()}\n"
        f"*Detalle:* {detalle}\n"
        f"*Hora:* {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Panel: http://localhost:8000"
    )

    cfg = cargar_config_mensajeria()
    resultados = {}

    def _tarea_envio():
        # 1. WhatsApp
        if cfg.get("whatsapp", {}).get("habilitado"):
            ok_wa, res_wa = enviar_whatsapp(mensaje_texto)
            print(f"[MENSAJERÍA WhatsApp] {res_wa}")

        # 2. Telegram
        if cfg.get("telegram", {}).get("habilitado"):
            ok_tg, res_tg = enviar_telegram(mensaje_texto)
            print(f"[MENSAJERÍA Telegram] {res_tg}")

        # 3. Cisco Webex
        if cfg.get("webex", {}).get("habilitado"):
            ok_wx, res_wx = enviar_webex(mensaje_texto)
            print(f"[MENSAJERÍA Webex] {res_wx}")

    # Enviar en un hilo independiente para no congelar la API ni el streaming
    hilo = threading.Thread(target=_tarea_envio, daemon=True)
    hilo.start()

    return {"enviado": True, "titulo": titulo, "nivel": nivel}
