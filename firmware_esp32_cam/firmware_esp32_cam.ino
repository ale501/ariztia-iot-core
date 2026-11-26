/*
 * ==============================================================================
 * FIRMWARE ESP32-CAM — MODO RED PROPIA (ACCESS POINT DEDICADO)
 * ==============================================================================
 * Proyecto: Monitoreo & Tracking de Aves — Ariztía IoT
 *
 * ¡TOTALMENTE INDEPENDIENTE DE ROUTERS O INTERNET!
 * La cámara crea su propia red Wi-Fi inmediatamente al encenderse.
 *
 * Datos de la Red Wi-Fi:
 *   - Nombre de red (SSID): ARIZTIA_CAM_POLLOS
 *   - Contraseña Wi-Fi:     12345678
 *   - IP fija garantizada:  192.168.4.1
 *   - URL de streaming:     http://192.168.4.1:81/stream
 *
 * Configuración en Arduino IDE:
 *   - Placa: "AI Thinker ESP32-CAM" (o "ESP32 Wrover Module")
 *   - Partition Scheme: "Huge APP (3MB No OTA/1MB SPIFFS)"   <-- ¡OBLIGATORIO!
 *   - PSRAM: "Enabled"
 * ==============================================================================
 */

#include "esp_camera.h"
#include <WiFi.h>
#include "esp_http_server.h"

// ------------------------------------------------------------------------------
// 1. DATOS DE LA RED WI-FI QUE CREARÁ LA CÁMARA
// ------------------------------------------------------------------------------
const char* AP_SSID     = "ARIZTIA_CAM_POLLOS";
const char* AP_PASSWORD = "12345678";

// ------------------------------------------------------------------------------
// 2. DEFINICIÓN DE PINES PARA MODELO AI-THINKER ESP32-CAM
// ------------------------------------------------------------------------------
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

#define FLASH_LED_PIN      4  // LED flash blanco

#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t stream_httpd = NULL;

// Manejador del flujo de video continuo MJPEG
static esp_err_t stream_handler(httpd_req_t *req) {
  camera_fb_t * fb = NULL;
  esp_err_t res = ESP_OK;
  size_t _jpg_buf_len = 0;
  uint8_t * _jpg_buf = NULL;
  char * part_buf[64];

  res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
  if (res != ESP_OK) return res;

  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_hdr(req, "X-Framerate", "25");

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("[ERROR] No se pudo capturar cuadro");
      res = ESP_FAIL;
      break;
    }

    _jpg_buf_len = fb->len;
    _jpg_buf = fb->buf;

    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
    }
    if (res == ESP_OK) {
      size_t hlen = snprintf((char *)part_buf, 64, _STREAM_PART, _jpg_buf_len);
      res = httpd_resp_send_chunk(req, (const char *)part_buf, hlen);
    }
    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
    }

    esp_camera_fb_return(fb);
    fb = NULL;
    _jpg_buf = NULL;

    if (res != ESP_OK) break;
  }
  return res;
}

// Iniciar servidor HTTP de video en puerto 81
void iniciarServidorCamara() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 81;
  config.ctrl_port = 32769;

  httpd_uri_t stream_uri = {
    .uri       = "/stream",
    .method    = HTTP_GET,
    .handler   = stream_handler,
    .user_ctx  = NULL
  };

  if (httpd_start(&stream_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &stream_uri);
    Serial.println("[OK] Servidor de video activo en puerto 81");
  } else {
    Serial.println("[ERROR] Fallo al iniciar servidor de video");
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n==========================================================");
  Serial.println("  ESP32-CAM ARIZTÍA — MODO RED PROPIA AUTÓNOMA           ");
  Serial.println("==========================================================");

  // Configuración de hardware para lente OV2640
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // Resolución óptima para tracking de pollos sin retardo
  config.frame_size = FRAMESIZE_VGA;  // 640x480
  config.jpeg_quality = 12;           // Calidad nítida (10 a 63)
  config.fb_count = 2;                // Doble búfer para fluidez

  // Inicializar sensor de cámara
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[ERROR FATAL] Fallo al inicializar cámara: 0x%x\n", err);
    Serial.println("Revisa que el flex naranja del lente esté bien presionado.");
    return;
  }
  Serial.println("[OK] Lente OV2640 inicializado con éxito");

  // Ajustes de imagen para galpón avícola
  sensor_t * s = esp_camera_sensor_get();
  s->set_brightness(s, 1);
  s->set_contrast(s, 1);

  // --------------------------------------------------------------------------
  // CREACIÓN DE RED WI-FI PROPIA (MODO ACCESS POINT)
  // --------------------------------------------------------------------------
  WiFi.mode(WIFI_AP);
  // IP fija estándar: 192.168.4.1
  IPAddress local_IP(192, 168, 4, 1);
  IPAddress gateway(192, 168, 4, 1);
  IPAddress subnet(255, 255, 255, 0);

  WiFi.softAPConfig(local_IP, gateway, subnet);
  bool apOk = WiFi.softAP(AP_SSID, AP_PASSWORD, 1, 0, 4);

  if (apOk) {
    Serial.println("[OK] Red Wi-Fi autónoma creada correctamente!");
    Serial.printf("     Nombre de Wi-Fi:  %s\n", AP_SSID);
    Serial.printf("     Contraseña:       %s\n", AP_PASSWORD);
    Serial.println("     IP de la cámara:  192.168.4.1");
    Serial.println("----------------------------------------------------------");
    Serial.println(" >>> URL DE VIDEO PARA PYTHON (prueba.py):             <<<");
    Serial.println(" >>> http://192.168.4.1:81/stream                      <<<");
    Serial.println("----------------------------------------------------------");
    iniciarServidorCamara();
  } else {
    Serial.println("[ERROR] No se pudo crear la red Wi-Fi propia");
  }
}

void loop() {
  // Transmisión en segundo plano
  delay(10000);
}
