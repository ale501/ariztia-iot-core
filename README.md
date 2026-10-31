# Sistema de Monitoreo Ambiental y Tracking — Ariztía

Proyecto IoT para monitoreo de temperatura, humedad (IEC) y tracking de pollos en pabellón avícola.

## Arquitectura

```
[ ESP32 (COM6) ] → [ bridge_sensores.py ] → [ app_ariztia.py :5001 ] → [ Prometheus :9090 ] → [ Grafana :3000 ]
[ ESP32-CAM    ] → [ prueba.py :5000    ] → [ OpenCV Tracking       ]
                         ↑
              [ iniciar.py — Orquestador ]
                         ↑
              [ login.html + menu.html :8000 ]
```

## Requisitos

- Python 3.11+
- Arduino IDE (para el firmware del ESP32)
- Prometheus (descargado en la carpeta del proyecto)
- Grafana (descargado en la carpeta del proyecto)

## Instalación rápida

```powershell
# 1. Crear entorno virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Arrancar todo
python iniciar.py
```

## Servicios disponibles

| Servicio | URL | Descripción |
|---|---|---|
| Login / Menú | http://localhost:8000 | Interfaz principal |
| Tracking | http://localhost:5000 | Video y detección de pollos |
| Monitoreo IEC | http://localhost:5001 | Temperatura, humedad, alertas |
| Prometheus | http://localhost:9090 | Métricas en tiempo real |
| Grafana | http://localhost:3000 | Dashboards visuales |

## Ensayos de prueba disponibles

En `http://localhost:5001` puedes activar:
- **Normal** (22–25.5 °C)
- **Advertencia** (27–30 °C)
- **Crítico** (>35 °C)
- **Lectura inválida** (falla de sensor)
- **Conexión intermitente** (caída de señal)

## Hardware soportado

- **ESP32** con sensor DHT22 (temperatura y humedad) por USB (COM6)
- **ESP32-CAM** para video de tracking por Wi-Fi (192.168.4.1:81)

## Firmware ESP32

Abre `firmware_esp32/firmware_esp32.ino` en Arduino IDE:
- Placa: `ESP32 Dev Module`
- Puerto: `COM6`

## Configuración de hardware

Edita `config_hardware.json` para cambiar IPs, puertos COM y más sin tocar código Python.
