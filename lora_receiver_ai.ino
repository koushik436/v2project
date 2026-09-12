#include <SPI.h>
#include <LoRa.h>

// -------- LoRa pins --------
#define LORA_SS 5
#define LORA_RST 14
#define LORA_DIO0 2

// -------- Rule thresholds --------
const float TEMP_WARNING_MIN = 29.0;
const float TEMP_CRITICAL = 33.0;
const float CURRENT_CRITICAL = 1.2;
const float VOLTAGE_CRITICAL = 3.5;

const float CURRENT_WARNING = 1.0;
const float VOLTAGE_WARNING = 3.7;

unsigned long malformedPackets = 0;
unsigned long crcFailures = 0;
unsigned long sequenceGaps = 0;
unsigned long packetCount = 0;
unsigned long lastSequence = 0;
bool hasLastSequence = false;

unsigned long fnv1a32(const String &text) {
  unsigned long hash = 2166136261UL;
  for (unsigned int i = 0; i < text.length(); i++) {
    hash ^= (unsigned char)text.charAt(i);
    hash *= 16777619UL;
  }
  return hash;
}

unsigned long hexToULong(const String &value) {
  return strtoul(value.c_str(), nullptr, 16);
}

bool parseLegacyPayload(const String &received, float &temp, float &current, float &voltage, String &status) {
  int first = received.indexOf(',');
  int second = received.indexOf(',', first + 1);
  int third = received.indexOf(',', second + 1);

  if (first <= 0 || second <= first || third <= second) {
    return false;
  }

  temp = received.substring(0, first).toFloat();
  current = received.substring(first + 1, second).toFloat();
  voltage = received.substring(second + 1, third).toFloat();
  status = received.substring(third + 1);
  status.trim();

  return status.length() > 0;
}

bool parseV2Payload(
    const String &received,
    float &temp,
    float &current,
    float &voltage,
    String &status,
    String &deviceId,
    unsigned long &sequence,
    String &relayState,
    bool &failSafe) {
  int delimiterCount = 0;
  for (unsigned int i = 0; i < received.length(); i++) {
    if (received.charAt(i) == '|') {
      delimiterCount++;
    }
  }
  if (delimiterCount != 11) {
    return false;
  }

  int indexes[12];
  int indexPos = 0;
  indexes[indexPos++] = -1;
  for (unsigned int i = 0; i < received.length(); i++) {
    if (received.charAt(i) == '|') {
      indexes[indexPos++] = i;
    }
  }
  indexes[indexPos] = received.length();

  String fields[12];
  for (int i = 0; i < 12; i++) {
    fields[i] = received.substring(indexes[i] + 1, indexes[i + 1]);
    fields[i].trim();
  }

  if (fields[0] != "V2") {
    return false;
  }

  int lastPipe = received.lastIndexOf('|');
  if (lastPipe <= 0) {
    return false;
  }

  String body = received.substring(0, lastPipe);
  String crcHex = fields[11];
  unsigned long expectedCrc = fnv1a32(body);
  unsigned long actualCrc = hexToULong(crcHex);
  if (expectedCrc != actualCrc) {
    crcFailures++;
    return false;
  }

  deviceId = fields[1];
  sequence = strtoul(fields[3].c_str(), nullptr, 10);
  temp = fields[5].toFloat();
  current = fields[6].toFloat();
  voltage = fields[7].toFloat();
  status = fields[8];
  relayState = fields[9];
  failSafe = (fields[10] == "1");

  if (status.length() == 0) {
    return false;
  }

  if (hasLastSequence && sequence > lastSequence + 1) {
    sequenceGaps += (sequence - lastSequence - 1);
  }
  hasLastSequence = true;
  lastSequence = sequence;

  return true;
}

String classifyRisk(float temp, float current, float voltage, const String &status) {
  String normalizedStatus = status;
  normalizedStatus.trim();
  normalizedStatus.toUpperCase();

  if (temp > TEMP_CRITICAL || current > CURRENT_CRITICAL || voltage < VOLTAGE_CRITICAL) {
    return "Critical";
  }

  bool tempWarningBand = (temp >= TEMP_WARNING_MIN && temp <= TEMP_CRITICAL);
  if (tempWarningBand || current >= CURRENT_WARNING || voltage <= VOLTAGE_WARNING || normalizedStatus == "DISCONNECTED") {
    return "Warning";
  }

  return "Normal";
}

void setup() {
  Serial.begin(9600);

  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  if (!LoRa.begin(433E6)) {
    Serial.println("LoRa init failed");
    while (1) {
      delay(100);
    }
  }

  Serial.println("LoRa receiver ready");
}

void loop() {
  int packetSize = LoRa.parsePacket();
  if (!packetSize) {
    return;
  }

  String received = "";
  while (LoRa.available()) {
    received += (char)LoRa.read();
  }

  float temp = 0.0;
  float current = 0.0;
  float voltage = 0.0;
  String status = "";
  String deviceId = "legacy";
  unsigned long sequence = 0;
  String relayState = "-";
  bool failSafe = false;

  bool parsed = false;
  if (received.startsWith("V2|")) {
    parsed = parseV2Payload(received, temp, current, voltage, status, deviceId, sequence, relayState, failSafe);
    if (!parsed) {
      malformedPackets++;
      Serial.print("Parse/CRC error: ");
      Serial.println(received);
      Serial.print("Stats packets=");
      Serial.print(packetCount);
      Serial.print(" malformed=");
      Serial.print(malformedPackets);
      Serial.print(" crc_fail=");
      Serial.print(crcFailures);
      Serial.print(" seq_gaps=");
      Serial.println(sequenceGaps);
      return;
    }
  } else {
    parsed = parseLegacyPayload(received, temp, current, voltage, status);
    if (!parsed) {
      malformedPackets++;
      Serial.print("Parse error: ");
      Serial.println(received);
      return;
    }
  }

  packetCount++;

  String aiPrediction = classifyRisk(temp, current, voltage, status);

  // Output as CSV for backend ingestion
  Serial.print(temp, 2);
  Serial.print(",");
  Serial.print(current, 2);
  Serial.print(",");
  Serial.print(voltage, 2);
  Serial.print(",");
  Serial.println(status);
}
