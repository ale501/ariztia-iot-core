/*
 * ==============================================================================
 * FIRMWARE INTEGRAL ESP32 — ESTACIÓN AVÍCOLA ARIZTÍA IoT
 * ==============================================================================
 * Asignación Oficial de Pines:
 *   - DHT11 (T° y Humedad Aire):  Pin D4 (GPIO 4)
 *   - Horquilla (Humedad Suelo):  Pin D34 (GPIO 34 / ADC1)
 *   - LED Verde (Confort):        Pin D18 (GPIO 18)
 *   - LED Amarillo (Precaución):  Pin D19 (GPIO 19)
 *   - LED Rojo (Crítico >35°C):   Pin D21 (GPIO 21)
 *   - Buzzer (Alarma acústica):   Pin D25 (GPIO 25)
 *   - Relé (Extractor / Vent.):   Pin D26 (GPIO 26)
 *
 * Salida: JSON serial por USB (COM6 a 115200 baudios)
 * ==============================================================================
 */

#define PIN_DHT        4    // Sensor ambiental DHT11
#define PIN_SUELO      34   // Sensor horquilla humedad de suelo/cama (ADC1)
#define LED_VERDE      18   // Confort
#define LED_AMARILLO   19   // Precaución (27-30 °C)
#define LED_ROJO       21   // Crítico (>35 °C)
#define PIN_BUZZER     25   // Alarma acústica
#define PIN_RELE       26   // Actuador de ventilación

const unsigned long INTERVALO_ENVIO_MS = 3000;
unsigned long ultimoEnvio = 0;

float temperatura = 23.5;
float humedad = 55.0;
int humedadSuelo = 0;

// Lector de protocolo DHT11 sin librerías externas
bool leerDHT11(float &temp, float &hum) {
  uint8_t datos[5] = {0, 0, 0, 0, 0};

  pinMode(PIN_DHT, OUTPUT);
  digitalWrite(PIN_DHT, LOW);
  delay(20);
  digitalWrite(PIN_DHT, HIGH);
  delayMicroseconds(30);
  pinMode(PIN_DHT, INPUT_PULLUP);

  unsigned long timeout = micros();
  while (digitalRead(PIN_DHT) == HIGH) if (micros() - timeout > 100) return false;
  timeout = micros();
  while (digitalRead(PIN_DHT) == LOW) if (micros() - timeout > 100) return false;
  timeout = micros();
  while (digitalRead(PIN_DHT) == HIGH) if (micros() - timeout > 100) return false;

  for (int i = 0; i < 40; i++) {
    timeout = micros();
    while (digitalRead(PIN_DHT) == LOW) if (micros() - timeout > 100) return false;

    unsigned long tInicio = micros();
    while (digitalRead(PIN_DHT) == HIGH) if (micros() - tInicio > 150) return false;

    if ((micros() - tInicio) > 40) {
      datos[i / 8] |= (1 << (7 - (i % 8)));
    }
  }

  if (datos[4] == ((datos[0] + datos[1] + datos[2] + datos[3]) & 0xFF)) {
    hum = (float)datos[0];
    temp = (float)datos[2];
    return true;
  }
  return false;
}

// Lectura de la horquilla (sensor de suelo) en porcentaje 0 a 100%
int leerHumedadCama() {
  int valorRaw = analogRead(PIN_SUELO);
  // En seco el valor está cerca de 4095; en agua sumergido cerca de 1500
  int pct = map(valorRaw, 4095, 1500, 0, 100);
  return constrain(pct, 0, 100);
}

void actualizarSemaforoYAlarmas(float t, float h) {
  float iec = t + h;

  // 1. Escenario Crítico (> 35 °C o IEC >= 105)
  if (t >= 35.0 || iec >= 105.0) {
    digitalWrite(LED_VERDE, LOW);
    digitalWrite(LED_AMARILLO, LOW);
    digitalWrite(LED_ROJO, HIGH);
    digitalWrite(PIN_RELE, HIGH);   // Activa extractor
    
    // Tono de alarma acústica intermitente
    digitalWrite(PIN_BUZZER, HIGH);
    delay(80);
    digitalWrite(PIN_BUZZER, LOW);
  }
  // 2. Escenario Advertencia / Precaución (27 a 30 °C o IEC 95-104)
  else if (t >= 27.0 || iec >= 95.0) {
    digitalWrite(LED_VERDE, LOW);
    digitalWrite(LED_AMARILLO, HIGH);
    digitalWrite(LED_ROJO, LOW);
    digitalWrite(PIN_RELE, HIGH);   // Activa ventilación preventiva
    digitalWrite(PIN_BUZZER, LOW);
  }
  // 3. Escenario Confort Normal (< 27 °C)
  else {
    digitalWrite(LED_VERDE, HIGH);
    digitalWrite(LED_AMARILLO, LOW);
    digitalWrite(LED_ROJO, LOW);
    digitalWrite(PIN_RELE, LOW);    // Ventilación en reposo
    digitalWrite(PIN_BUZZER, LOW);
  }
}

void setup() {
  Serial.begin(115200);

  // Configurar pines de actuadores
  pinMode(LED_VERDE, OUTPUT);
  pinMode(LED_AMARILLO, OUTPUT);
  pinMode(LED_ROJO, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_RELE, OUTPUT);

  // Estado inicial seguro
  digitalWrite(LED_VERDE, HIGH);
  digitalWrite(LED_AMARILLO, LOW);
  digitalWrite(LED_ROJO, LOW);
  digitalWrite(PIN_BUZZER, LOW);
  digitalWrite(PIN_RELE, LOW);

  analogReadResolution(12); // ADC a 12 bits (0 a 4095)

  delay(1000);
  Serial.println("\n==========================================================");
  Serial.println("  ESTACIÓN AVÍCOLA ARIZTÍA - HARDWARE INTEGRAL ACTIVO    ");
  Serial.println("==========================================================");
}

void loop() {
  unsigned long ahora = millis();

  if (ahora - ultimoEnvio >= INTERVALO_ENVIO_MS || ultimoEnvio == 0) {
    ultimoEnvio = ahora;

    float t = 0.0, h = 0.0;
    bool dhtOk = leerDHT11(t, h);

    if (dhtOk && t > 0.0 && h > 0.0) {
      temperatura = t;
      humedad = h;
    }

    humedadSuelo = leerHumedadCama();

    // Actualiza semáforo LED, relé de ventilación y alarma sonora
    actualizarSemaforoYAlarmas(temperatura, humedad);

    // Emisión de telemetría completa por USB
    Serial.printf("{\"temperatura\": %.1f, \"humedad\": %.1f, \"suelo\": %d}\n",
                  temperatura, humedad, humedadSuelo);
  }

  delay(50);
}
