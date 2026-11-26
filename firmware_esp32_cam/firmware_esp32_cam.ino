/*
 * ==============================================================================
 * FIRMWARE STREAMING MJPEG PARA ESP32-CAM (AI-THINKER OV2640)
 * ==============================================================================
 * Proyecto: Monitoreo & Tracking de Aves — Ariztía IoT
 *
 * Entrega video en vivo para 'prueba.py' en:
 *    http://<IP_CAMARA>:81/stream
 *
 * Configuración en Arduino IDE:
 *   - Placa: "AI Thinker ESP32-CAM"  (o "ESP32 Wrover Module")
 *   - Partition Scheme: "Huge APP (3MB No OTA/1MB SPIFFS)"   <-- ¡MUY IMPORTANTE!
 *   - CPU Frequency: 240MHz
 *   - Flash Frequency: 80MHz
 *   - PSRAM: "Enabled"
 * ==============================================================================
 */

#include "esp_camera.h"
#include <WiFi.h>
#include "esp_http_server.h"

// ------------------------------------------------------------------------------
// 1. CONFIGURACIÓN DE TU RED WI-FI (Opcional)
// ------------------------------------------------------------------------------
// Si dejas tu WiFi configurado, se conectará a tu router.
// Si no logra conectar en 10 segundos, ¡creará su propia red Wi-Fi automáticamente!
const char* WIFI_SSID     = "TU_WIFI_AQUI";        // Escribe el nombre de tu Wi-Fi
const char* WIFI_PASSWORD = "TU_CONTRASEÑA_AQUI";  // Escribe la contraseña de tu Wi-Fi

// Nombre y clave de la red Wi-Fi propia que creará si no hay router:
const char* AP_SSID       = "ESP32_CAM_ARIZTIA";
const char* AP_PASSWORD   = "12345678";

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

#define FLASH_LED_PIN      4  // LED flash blanco potente

#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t stream_httpd = NULL;

// ------------------------------------------------------------------------------
// 3. MANEJADOR DE STREAMING MJPEG
// ------------------------------------------------------------------------------
static esp_err_t stream_handler(httpd_req_t *req) {
  camera_fb_t * fb = NULL;
  esp_err_t res = ESP_OK;
  size_t _jpg_buf_len = 0;
  uint8_t * _jpg_buf = NULL;
  char * part_buf[64];

  res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
  if (res != ESP_OK) return res;

  // Encabezados para evitar caché y latencia
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_hdr(req, "X-Framerate", "25");

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("[ERROR] Fallo al capturar cuadro de la cámara");
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

// Iniciar servidor HTTP en el puerto 81
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
    Serial.println("[OK] Servidor de video iniciado exitosamente en puerto 81");
  } else {
    Serial.println("[ERROR] No se pudo iniciar el servidor HTTP");
  }
}

// ------------------------------------------------------------------------------
// SETUP
// ------------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n========================================================");
  Serial.println("   INICIANDO TRANSMISOR DE VIDEO - ESP32-CAM ARIZTÍA    ");
  Serial.println("========================================================");

  // Configuración del sensor OV2640
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
  config.pin_siod = SIOD_GPIO_NUM;
  config.pin_sioc = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // Resolución óptima para tracking de pollos sin delay
  config.frame_size = FRAMESIZE_VGA;  // 640x480 (Ideal para OpenCV)
  config.jpeg_quality = 12;           // Calidad buena (10-63, menor es mejor)
  config.fb_count = 2;                // Doble buffer para máxima fluidez

  // Inicializar hardware de cámara
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[ERROR FATAL] Fallo al iniciar cámara OV2640: 0x%x\n", err);
    Serial.println("Revisa que el cable plano naranja del lente esté bien insertado.");
    return;
  }
  Serial.println("[OK] Cámara OV2640 inicializada correctamente");

  // Ajustes de imagen para avicultura
  sensor_t * s = esp_camera_sensor_get();
  s->set_brightness(s, 1);     // Brillo adecuado para galpón
  s->set_contrast(s, 1);       // Contraste para resaltar contornos de pollos
  s->set_saturation(s, 0);

  // Intentar conectar a red Wi-Fi configurada
  Serial.printf("\nIntentando conectar a Wi-Fi: %s ...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int intentos = 0;
  while (WiFi.status() != WL_CONNECTED && intentos < 15) {
    delay(500);
    Serial.print(".");
    intentos++;
  }

  // Si no se conectó al router, crear Punto de Acceso propio (Access Point)
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[OK] Conectado a tu red Wi-Fi doméstica");
    Serial.print("Dirección IP asignada: ");
    Serial.println(WiFi.localIP());
    iniciarServidorCamara();
    Serial.printf("\n>>> URL PARA PYTHON (prueba.py): http://%s:81/stream <<<\n\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[AVISO] No se pudo conectar al router. Creando red propia...");
    WiFi.mode(WIFI_AP);
    WiFi.softAP(AP_SSID, AP_PASSWORD);
    IPAddress IP = WiFi.softAPIP();
    iniciarServidorCamara();

    Serial.printf("[OK] Red Wi-Fi creada: '%s' | Clave: '%s'\n", AP_SSID, AP_PASSWORD);
    Serial.print("Dirección IP fija: ");
    Serial.println(IP);
    Serial.printf("\n>>> URL PARA PYTHON (prueba.py): http://%s:81/stream <<<\n\n", IP.toString().c_str());
  }
}

void loop() {
  // El servidor de video corre en segundo plano en los hilos del ESP32
  delay(10000);
}
