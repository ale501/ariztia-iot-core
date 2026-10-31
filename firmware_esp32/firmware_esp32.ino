/*
 * ==============================================================================
 * FIRMWARE ESP32 - MODO LOCAL DIRECTO POR CABLE USB (COM6)
 * ==============================================================================
 * ¡Listo para compilar y subir de inmediato!
 * - NO requiere instalar ninguna librería externa en Arduino IDE.
 * - Conexión 100% LOCAL por el puerto USB COM6.
 * - Transmite las lecturas de temperatura y humedad en formato JSON.
 * ==============================================================================
 */

#define LED_PIN 2   // LED azul integrado en el ESP32

// Muestreo: envía una lectura cada 3 segundos
const unsigned long INTERVALO_ENVIO_MS = 3000;
unsigned long ultimoEnvio = 0;

// Valores iniciales para la simulación local en el microcontrolador
float temperatura = 24.5;
float humedad = 55.0;

void setup() {
  // Comunicación local directa por cable USB a 115200 baudios (coincide con Python)
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  delay(1000);

  Serial.println("\n==================================================");
  Serial.println("  ESP32 LOCAL ACTIVO - MONITOREO ARIZTÍA (COM6)   ");
  Serial.println("==================================================");
}

void loop() {
  unsigned long ahora = millis();

  if (ahora - ultimoEnvio >= INTERVALO_ENVIO_MS || ultimoEnvio == 0) {
    ultimoEnvio = ahora;

    // 1. Parpadeo rápido del LED indicador en el ESP32 al transmitir
    digitalWrite(LED_PIN, HIGH);
    delay(60);
    digitalWrite(LED_PIN, LOW);

    // 2. Generación de variaciones térmicas realistas desde el microcontrolador
    // (Cuando te llegue el sensor físico, reemplazaremos esto por la lectura del pin)
    temperatura += ((random(0, 11) - 5) / 10.0);
    if (temperatura < 22.0) temperatura = 22.8;
    if (temperatura > 31.0) temperatura = 30.2;

    humedad += ((random(0, 11) - 5) / 10.0);
    if (humedad < 45.0) humedad = 48.0;
    if (humedad > 68.0) humedad = 65.0;

    // 3. ENVÍO LOCAL DIRECTO POR USB (COM6)
    // Este JSON lo recibe 'bridge_sensores.py' y lo reenvía a tu web y Grafana
    Serial.printf("{\"temperatura\": %.1f, \"humedad\": %.1f}\n", temperatura, humedad);
  }

  delay(50);
}
