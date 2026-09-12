#include <SPI.h>
#include <LoRa.h>
#include <Wire.h>
#include <Adafruit_INA219.h>
#include "DHT.h"

// -------- DHT --------
#define DHTPIN 4
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

// -------- INA219 --------
Adafruit_INA219 ina219;

// -------- LoRa pins --------
#define LORA_SS 5
#define LORA_RST 14
#define LORA_DIO0 2

// -------- Actuators --------
#define RELAY_PIN 26
#define BUZZER_PIN 27
#define LED_PIN 25

// -------- ESP status threshold --------
const float TEMP_DISCONNECT = 29.0;
const int MAX_SENSOR_FAILS = 3;

const char *DEVICE_ID = "ESP32_TX_01";
const int PACKET_VERSION = 2;

unsigned long packetSequence = 0;
int consecutiveSensorFailures = 0;
bool failSafeActive = false;
String lastStatus = "CONNECTED";
int lastRelayState = HIGH;

unsigned long fnv1a32(const String &text) {
  unsigned long hash = 2166136261UL;
  for (unsigned int i = 0; i < text.length(); i++) {
    hash ^= (unsigned char)text.charAt(i);
    hash *= 16777619UL;
  }
  return hash;
}

String toHex8(unsigned long value) {
  char buffer[9];
  sprintf(buffer, "%08lX", value);
  return String(buffer);
}

void auditRelayEvent(const String &reason, int relayState, const String &status, float temperature, float current, float voltage) {
  String event = "AUDIT," +
                 String(millis()) + "," +
                 reason + "," +
                 String(relayState == HIGH ? "ON" : "OFF") + "," +
                 status + "," +
                 String(temperature, 2) + "," +
                 String(current, 3) + "," +
                 String(voltage, 3);
  Serial.println(event);
}

void applySafetyOutputs(bool disconnected, const String &reason, float temperature, float current, float voltage) {
  int desiredRelay = disconnected ? LOW : HIGH;
  int desiredBuzzer = disconnected ? HIGH : LOW;
  int desiredLed = disconnected ? HIGH : LOW;
  String status = disconnected ? "DISCONNECTED" : "CONNECTED";

  digitalWrite(RELAY_PIN, desiredRelay);
  digitalWrite(BUZZER_PIN, desiredBuzzer);
  digitalWrite(LED_PIN, desiredLed);

  if (desiredRelay != lastRelayState || status != lastStatus) {
    auditRelayEvent(reason, desiredRelay, status, temperature, current, voltage);
  }

  lastRelayState = desiredRelay;
  lastStatus = status;
}

void setup() {
  Serial.begin(9600);

  dht.begin();
  ina219.begin();

  pinMode(RELAY_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);

  // Safe ON state (relay connected, no alarm)
  digitalWrite(RELAY_PIN, HIGH);
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(LED_PIN, LOW);

  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  if (!LoRa.begin(433E6)) {
    Serial.println("LoRa failed");
    while (1) {
      delay(100);
    }
  }

  Serial.println("Transmitter ready");
}

void loop() {
  float temperature = dht.readTemperature();
  float voltage = ina219.getBusVoltage_V();
  float current = ina219.getCurrent_mA() / 1000.0;

  if (isnan(temperature) || isnan(voltage) || isnan(current)) {
    consecutiveSensorFailures++;
    Serial.println("Sensor read error");

    if (consecutiveSensorFailures >= MAX_SENSOR_FAILS) {
      failSafeActive = true;
      applySafetyOutputs(true, "SENSOR_FAILSAFE", 0.0, 0.0, 0.0);
      Serial.println("FAILSAFE,SENSOR_READ_FAILURE");
    }

    delay(1000);
    return;
  }

  consecutiveSensorFailures = 0;
  failSafeActive = false;

  bool disconnected = (temperature >= TEMP_DISCONNECT);
  applySafetyOutputs(disconnected, "TEMP_POLICY", temperature, current, voltage);

  String status = disconnected ? "DISCONNECTED" : "CONNECTED";
  String relayState = (lastRelayState == HIGH) ? "ON" : "OFF";

  packetSequence++;
  String payloadBody = "V2|" +
                       String(DEVICE_ID) + "|" +
                       String(PACKET_VERSION) + "|" +
                       String(packetSequence) + "|" +
                       String(millis()) + "|" +
                       String(temperature, 2) + "|" +
                       String(current, 3) + "|" +
                       String(voltage, 3) + "|" +
                       status + "|" +
                       relayState + "|" +
                       String(failSafeActive ? "1" : "0");

  String checksum = toHex8(fnv1a32(payloadBody));
  String payloadV2 = payloadBody + "|" + checksum;

  String payload = String(temperature, 2) + "," +
                   String(current, 3) + "," +
                   String(voltage, 2) + "," +
                   status;

  // Keep legacy CSV line for existing serial consumers.
  Serial.println(payload);

  LoRa.beginPacket();
  LoRa.print(payloadV2);
  LoRa.endPacket();

  delay(1000);
}
