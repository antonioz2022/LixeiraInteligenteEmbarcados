#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Crie include/secrets.h a partir de include/secrets.example.h"
#endif

// Pinos do projeto (versao corrigida para evitar GPIO de strapping)
static const uint8_t PIN_US_TRIG = 5;
static const uint8_t PIN_US_ECHO = 18;   // ECHO deve vir com divisor 1k/2k
static const uint8_t PIN_IR_OUT = 19;
static const uint8_t PIN_BTN_OIL = 4;
static const uint8_t PIN_BTN_SOLID = 13;
static const uint8_t PIN_LED_R = 25;
static const uint8_t PIN_LED_G = 26;
static const uint8_t PIN_LED_B = 27;

static const bool IR_ACTIVE_LOW = true;
static const float BIN_DEPTH_CM = 30.0f;           // Ajuste conforme profundidade real
static const float FULL_THRESHOLD_PCT = 85.0f;
static const float CLEAR_THRESHOLD_PCT = 70.0f;  // histerese: so "desincha" abaixo disto
static const unsigned long TELEMETRY_INTERVAL_MS = 2000;
static const unsigned long DEBOUNCE_MS = 40;

static const char* TOPIC_TELEMETRY = "smartbin/telemetry";
static const char* TOPIC_DISCARD = "smartbin/discard";

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

float lastOilLevelPct = 0.0f;
float lastSolidLevelPct = 0.0f;
bool lastIrFull = false;
unsigned long lastTelemetryAt = 0;

unsigned long ledOverrideUntil = 0;
uint8_t ledOverrideR = 0;
uint8_t ledOverrideG = 0;
uint8_t ledOverrideB = 0;

struct ButtonState {
  uint8_t pin;
  const char* wasteType;
  bool lastReading;
  bool stableState;
  unsigned long lastDebounceAt;
};

ButtonState buttonOil{PIN_BTN_OIL, "oleo", LOW, LOW, 0};
ButtonState buttonSolid{PIN_BTN_SOLID, "solido", LOW, LOW, 0};

float clampPct(float value) {
  if (value < 0.0f) return 0.0f;
  if (value > 100.0f) return 100.0f;
  return value;
}

void setRgb(uint8_t r, uint8_t g, uint8_t b) {
  digitalWrite(PIN_LED_R, r ? HIGH : LOW);
  digitalWrite(PIN_LED_G, g ? HIGH : LOW);
  digitalWrite(PIN_LED_B, b ? HIGH : LOW);
}

void setTemporaryColor(uint8_t r, uint8_t g, uint8_t b, unsigned long durationMs) {
  ledOverrideR = r;
  ledOverrideG = g;
  ledOverrideB = b;
  ledOverrideUntil = millis() + durationMs;
}

void updateLed() {
  if (millis() < ledOverrideUntil) {
    setRgb(ledOverrideR, ledOverrideG, ledOverrideB);
    return;
  }

  // Histerese: entra em "cheio" em FULL_THRESHOLD e so sai abaixo de
  // CLEAR_THRESHOLD, evitando o LED piscar quando o nivel oscila na borda.
  static bool latchedFull = false;
  const float maxLevel = max(lastOilLevelPct, lastSolidLevelPct);
  if (!latchedFull && maxLevel >= FULL_THRESHOLD_PCT) {
    latchedFull = true;
  } else if (latchedFull && maxLevel <= CLEAR_THRESHOLD_PCT) {
    latchedFull = false;
  }

  if (latchedFull) {
    setRgb(1, 0, 0);  // vermelho quando algum compartimento estah cheio
  } else {
    setRgb(0, 0, 0);  // sem evento, LED apagado
  }
}

void connectWiFiIfNeeded() {
  static unsigned long lastAttempt = 0;
  if (WiFi.status() == WL_CONNECTED) return;
  if (millis() - lastAttempt < 5000) return;

  lastAttempt = millis();
  Serial.printf("[WiFi] Conectando em %s...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void connectMqttIfNeeded() {
  static unsigned long lastAttempt = 0;
  if (WiFi.status() != WL_CONNECTED) return;
  if (mqttClient.connected()) return;
  if (millis() - lastAttempt < 4000) return;

  lastAttempt = millis();
  Serial.printf("[MQTT] Conectando em %s:%u...\n", MQTT_HOST, MQTT_PORT);

  const bool ok = mqttClient.connect(
      "esp32-smartbin",
      MQTT_USER,
      MQTT_PASSWORD);

  if (ok) {
    Serial.println("[MQTT] Conectado.");
  } else {
    Serial.printf("[MQTT] Falhou rc=%d\n", mqttClient.state());
  }
}

float readDistanceOnceCm() {
  digitalWrite(PIN_US_TRIG, LOW);
  delayMicroseconds(3);
  digitalWrite(PIN_US_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_US_TRIG, LOW);

  const unsigned long duration = pulseIn(PIN_US_ECHO, HIGH, 30000UL);
  if (duration == 0) {
    return -1.0f;
  }
  // cm = (tempo_us * velocidade_som_cm/us) / 2
  return (duration * 0.0343f) / 2.0f;
}

float readDistanceCm() {
  // O HC-SR04 produz picos espurios; usamos a mediana de varias amostras
  // para descartar leituras isoladas ruins (ex: eco fora de fase).
  static const uint8_t SAMPLES = 5;
  float readings[SAMPLES];
  uint8_t valid = 0;

  for (uint8_t i = 0; i < SAMPLES; i++) {
    const float d = readDistanceOnceCm();
    if (d >= 0.0f) {
      readings[valid++] = d;
    }
    delay(8);  // intervalo minimo entre disparos para evitar eco residual
  }

  if (valid == 0) {
    return -1.0f;
  }

  // Insertion sort (vetor minusculo) e seleciona a mediana das leituras validas.
  for (uint8_t i = 1; i < valid; i++) {
    const float key = readings[i];
    int8_t j = i - 1;
    while (j >= 0 && readings[j] > key) {
      readings[j + 1] = readings[j];
      j--;
    }
    readings[j + 1] = key;
  }
  return readings[valid / 2];
}

float readOilLevelPct() {
  float distance = readDistanceCm();
  if (distance < 0.0f) {
    return lastOilLevelPct;
  }
  const float level = (1.0f - (distance / BIN_DEPTH_CM)) * 100.0f;
  return clampPct(level);
}

bool readIrFull() {
  const int raw = digitalRead(PIN_IR_OUT);
  return IR_ACTIVE_LOW ? (raw == LOW) : (raw == HIGH);
}

void publishTelemetry() {
  if (!mqttClient.connected()) return;

  lastOilLevelPct = readOilLevelPct();
  lastIrFull = readIrFull();
  // Sem segundo ultrassonico: nivel de solido derivado do IR
  lastSolidLevelPct = lastIrFull ? 100.0f : 0.0f;

  char payload[220];
  snprintf(
      payload,
      sizeof(payload),
      "{\"nivel_oleo_pct\":%.2f,\"nivel_solido_pct\":%.2f,\"ir_cheio\":%s,\"device_ms\":%lu}",
      lastOilLevelPct,
      lastSolidLevelPct,
      lastIrFull ? "true" : "false",
      millis());

  const bool sent = mqttClient.publish(TOPIC_TELEMETRY, payload, true);
  Serial.printf("[MQTT] telemetry %s: %s\n", sent ? "ok" : "erro", payload);
}

void publishDiscard(const char* wasteType) {
  if (!mqttClient.connected()) return;

  const bool oilSelected = strcmp(wasteType, "oleo") == 0;
  const bool blocked = oilSelected ? (lastOilLevelPct >= FULL_THRESHOLD_PCT)
                                   : (lastSolidLevelPct >= FULL_THRESHOLD_PCT);
  if (blocked) {
    // vermelho para indicar compartimento cheio
    setTemporaryColor(1, 0, 0, 650);
    Serial.printf("[EVT] descarte %s bloqueado (compartimento cheio)\n", wasteType);
    return;
  }

  char payload[120];
  snprintf(
      payload,
      sizeof(payload),
      "{\"tipo\":\"%s\",\"quantidade\":1,\"device_ms\":%lu}",
      wasteType,
      millis());

  const bool sent = mqttClient.publish(TOPIC_DISCARD, payload, false);
  Serial.printf("[MQTT] discard %s: %s\n", sent ? "ok" : "erro", payload);

  // Feedback: azul para oleo, verde para solido
  if (oilSelected) {
    setTemporaryColor(0, 0, 1, 500);
  } else {
    setTemporaryColor(0, 1, 0, 500);
  }
}

void handleButton(ButtonState& button) {
  const bool reading = digitalRead(button.pin);
  if (reading != button.lastReading) {
    button.lastDebounceAt = millis();
    button.lastReading = reading;
  }

  if ((millis() - button.lastDebounceAt) < DEBOUNCE_MS) {
    return;
  }

  if (reading != button.stableState) {
    button.stableState = reading;
    if (button.stableState == HIGH) {
      publishDiscard(button.wasteType);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n[BOOT] SmartBin ESP32 iniciando...");

  pinMode(PIN_US_TRIG, OUTPUT);
  pinMode(PIN_US_ECHO, INPUT);
  pinMode(PIN_IR_OUT, INPUT);

  // Pull-down externo no hardware; deixamos INPUT simples
  pinMode(PIN_BTN_OIL, INPUT);
  pinMode(PIN_BTN_SOLID, INPUT);

  pinMode(PIN_LED_R, OUTPUT);
  pinMode(PIN_LED_G, OUTPUT);
  pinMode(PIN_LED_B, OUTPUT);
  setRgb(0, 0, 0);

  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setBufferSize(256);

  connectWiFiIfNeeded();
}

void loop() {
  connectWiFiIfNeeded();
  connectMqttIfNeeded();

  if (mqttClient.connected()) {
    mqttClient.loop();
  }

  handleButton(buttonOil);
  handleButton(buttonSolid);

  if (millis() - lastTelemetryAt >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryAt = millis();
    publishTelemetry();
  }

  updateLed();
}
