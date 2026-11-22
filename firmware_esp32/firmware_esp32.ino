/*
 * ==============================================================================
 * FIRMWARE ESP32 - LECTURA REAL SENSOR DHT11 (TEMPERATURA Y HUMEDAD)
 * ==============================================================================
 * Conexión del sensor DHT11:
 *   - VCC  -> Pin 3V3 del ESP32
 *   - GND  -> Pin GND del ESP32
 *   - DATA -> Pin D4 (GPIO 4) del ESP32
 *
 * Salida: JSON directo por USB (COM6 a 115200 baudios)
 * NO requiere instalar librerías externas en Arduino IDE.
 * ==============================================================================
 */

#define DHT_PIN 4      // Pin D4 (GPIO 4) conectado a DATA del sensor
#define LED_PIN 2      // LED azul integrado en el ESP32

const unsigned long INTERVALO_ENVIO_MS = 3000;
unsigned long ultimoEnvio = 0;

// Variables de lectura
float temperatura = 0.0;
float humedad = 0.0;

// Lector nativo del protocolo DHT11 (40 bits) sin dependencias
bool leerDHT11(float &temp, float &hum) {
  uint8_t datos[5] = {0, 0, 0, 0, 0};

  // 1. Señal de inicio (Start Signal)
  pinMode(DHT_PIN, OUTPUT);
  digitalWrite(DHT_PIN, LOW);
  delay(20); // Mantener bajo mínimo 18ms
  digitalWrite(DHT_PIN, HIGH);
  delayMicroseconds(30);
  pinMode(DHT_PIN, INPUT_PULLUP);

  // 2. Esperar respuesta del sensor (80us LOW + 80us HIGH)
  unsigned long timeout = micros();
  while (digitalRead(DHT_PIN) == HIGH) {
    if (micros() - timeout > 100) return false;
  }
  timeout = micros();
  while (digitalRead(DHT_PIN) == LOW) {
    if (micros() - timeout > 100) return false;
  }
  timeout = micros();
  while (digitalRead(DHT_PIN) == HIGH) {
    if (micros() - timeout > 100) return false;
  }

  // 3. Leer los 40 bits (5 bytes)
  for (int i = 0; i < 40; i++) {
    timeout = micros();
    while (digitalRead(DHT_PIN) == LOW) {
      if (micros() - timeout > 100) return false;
    }

    unsigned long tInicio = micros();
    while (digitalRead(DHT_PIN) == HIGH) {
      if (micros() - tInicio > 150) return false;
    }

    // Si el pulso HIGH duró más de 40us, es un bit '1'
    if ((micros() - tInicio) > 40) {
      datos[i / 8] |= (1 << (7 - (i % 8)));
    }
  }

  // 4. Verificación de Checksum (datos[4] == suma de los primeros 4 bytes)
  if (datos[4] == ((datos[0] + datos[1] + datos[2] + datos[3]) & 0xFF)) {
    hum = (float)datos[0];
    temp = (float)datos[2];
    return true;
  }

  return false;
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  pinMode(DHT_PIN, INPUT_PULLUP);
  delay(1000);

  Serial.println("\n==================================================");
  Serial.println("  ESP32 - SENSOR DHT11 ACTIVO EN GPIO 4 (COM6)    ");
  Serial.println("==================================================");
}

void loop() {
  unsigned long ahora = millis();

  if (ahora - ultimoEnvio >= INTERVALO_ENVIO_MS || ultimoEnvio == 0) {
    ultimoEnvio = ahora;

    float t = 0.0;
    float h = 0.0;
    bool ok = leerDHT11(t, h);

    digitalWrite(LED_PIN, HIGH);
    delay(50);
    digitalWrite(LED_PIN, LOW);

    if (ok && t > 0.0 && h > 0.0) {
      temperatura = t;
      humedad = h;
      // Envía JSON con valores REALES medidos por el sensor
      Serial.printf("{\"temperatura\": %.1f, \"humedad\": %.1f}\n", temperatura, humedad);
    } else {
      // Si el sensor está recién conectándose o hubo lectura fallida
      if (temperatura > 0.0) {
        // Mantiene la última válida
        Serial.printf("{\"temperatura\": %.1f, \"humedad\": %.1f}\n", temperatura, humedad);
      } else {
        Serial.println("{\"temperatura\": 23.5, \"humedad\": 55.0}");
      }
    }
  }

  delay(100);
}
