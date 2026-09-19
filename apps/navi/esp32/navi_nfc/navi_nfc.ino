// NAVI badge reader: PN532 -> newline-delimited JSON on USB serial.
//
// Flash with Arduino IDE / arduino-cli (board "ESP32 Dev Module", 115200 baud)
// and install the "Adafruit PN532" library.
//
// Wiring, PN532 in HSU/UART mode (DIP switches 1=OFF 2=OFF):
//   PN532 VCC -> ESP32 3V3        PN532 TXD -> GPIO16  (ESP32 UART2 RX)
//   PN532 GND -> ESP32 GND        PN532 RXD -> GPIO17  (ESP32 UART2 TX)
//   PN532 RSTO -> GPIO5 (optional, only used for the hardware reset pulse)
// TX and RX cross over: the PN532's transmit goes to the ESP32's receive.
// For I2C or SPI instead, flip PN532_IFACE below and rewire per that block.
//
// The Jetson never sends anything except "ping\n", so the link stays one-way
// in practice and a reset mid-tap can only ever lose one tap.

#include <Adafruit_PN532.h>

#define PN532_IFACE_I2C 0
#define PN532_IFACE_SPI 1
#define PN532_IFACE_HSU 2
#define PN532_IFACE PN532_IFACE_HSU

#define PN532_IRQ 4
#define PN532_RESET 5
#define PN532_HSU_RX 16   // ESP32 receives here <- PN532 TXD
#define PN532_HSU_TX 17   // ESP32 transmits here -> PN532 RXD

#if PN532_IFACE == PN532_IFACE_I2C
Adafruit_PN532 nfc(PN532_IRQ, PN532_RESET);
static const char *IFACE_NAME = "i2c";
#elif PN532_IFACE == PN532_IFACE_SPI
// SCK=18 MISO=19 MOSI=23 SS=17
Adafruit_PN532 nfc(18, 19, 23, 17);
static const char *IFACE_NAME = "spi";
#else
Adafruit_PN532 nfc(PN532_RESET, &Serial2);
static const char *IFACE_NAME = "hsu";
#endif

// A tag sitting on the reader re-reads forever; only report changes, and only
// report it gone once it has been missing for a while (reads drop out a lot).
static const uint32_t READ_TIMEOUT_MS = 120;
static const uint32_t GONE_AFTER_MS = 700;
static const uint32_t REPEAT_AFTER_MS = 4000;

static String currentUid = "";
static uint32_t lastSeenMs = 0;
static uint32_t lastReportMs = 0;

static void emitBoot(const char *ver) {
  Serial.print("{\"t\":\"boot\",\"fw\":\"navi-nfc/1\",\"iface\":\"");
  Serial.print(IFACE_NAME);
  Serial.print("\",\"pn532\":\"");
  Serial.print(ver);
  Serial.println("\"}");
}

static void emitErr(const char *msg) {
  Serial.print("{\"t\":\"err\",\"msg\":\"");
  Serial.print(msg);
  Serial.println("\"}");
}

static String hexUid(const uint8_t *uid, uint8_t len) {
  String s;
  for (uint8_t i = 0; i < len; i++) {
    if (uid[i] < 0x10) s += '0';
    s += String(uid[i], HEX);
  }
  return s;
}

// Pull the first NDEF text record out of an NTAG21x user area, if there is one.
// Returns "" when the tag has no NDEF text (plain MIFARE, blank tag, ...).
static String readNdefText() {
  uint8_t data[4 * 12];
  for (uint8_t i = 0; i < 12; i++) {
    if (!nfc.ntag2xx_ReadPage(4 + i, data + i * 4)) return "";
  }

  // TLV walk: 0x03 = NDEF message, then length, then the record.
  uint8_t i = 0;
  const uint8_t n = sizeof(data);
  while (i < n && data[i] != 0x03) {
    if (data[i] == 0xFE) return "";        // terminator
    if (data[i] == 0x00) { i++; continue; }  // NULL TLV
    if (i + 1 >= n) return "";
    i += 2 + data[i + 1];                  // skip this TLV
  }
  if (i + 1 >= n) return "";

  uint8_t msgLen = data[i + 1];
  uint8_t p = i + 2;
  if (msgLen == 0xFF || p + 3 >= n) return "";

  uint8_t tnf = data[p] & 0x07;
  uint8_t typeLen = data[p + 1];
  uint8_t payloadLen = data[p + 2];
  uint8_t typePos = p + 3;
  if ((data[p] & 0x08) == 0) return "";              // not short-record
  if (tnf != 0x01 || typeLen != 1) return "";        // want well-known type
  if (data[typePos] != 'T') return "";              // want a Text record

  uint8_t payloadPos = typePos + typeLen;
  if (payloadPos >= n || payloadLen == 0) return "";
  uint8_t langLen = data[payloadPos] & 0x3F;         // status byte
  uint8_t textPos = payloadPos + 1 + langLen;
  int textLen = payloadLen - 1 - langLen;
  if (textLen <= 0 || textPos + textLen > n) return "";

  String out;
  for (int k = 0; k < textLen; k++) {
    char c = (char)data[textPos + k];
    if (c == '"' || c == '\\' || c < 0x20) continue;  // keep the JSON valid
    out += c;
  }
  return out;
}

void setup() {
  Serial.begin(115200);
  delay(200);

#if PN532_IFACE == PN532_IFACE_HSU
  // Set the pins before nfc.begin(), which re-opens Serial2 at 115200 and
  // keeps whatever pins are already configured.
  Serial2.begin(115200, SERIAL_8N1, PN532_HSU_RX, PN532_HSU_TX);
#endif

  nfc.begin();
  uint32_t version = nfc.getFirmwareVersion();
  if (!version) {
    emitErr("PN532 not found - check wiring and DIP switches");
    // Keep the port alive so the Jetson sees the error instead of silence.
    while (true) {
      delay(2000);
      emitErr("PN532 not found - check wiring and DIP switches");
    }
  }

  char ver[16];
  snprintf(ver, sizeof(ver), "%d.%d", (int)((version >> 16) & 0xFF),
           (int)((version >> 8) & 0xFF));
  nfc.SAMConfig();
  emitBoot(ver);
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "ping") Serial.println("{\"t\":\"pong\"}");
  }

  uint8_t uid[7] = {0};
  uint8_t uidLen = 0;
  bool found = nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLen,
                                       READ_TIMEOUT_MS);
  uint32_t now = millis();

  if (found && uidLen > 0) {
    String id = hexUid(uid, uidLen);
    bool isNew = (id != currentUid);
    bool stale = (now - lastReportMs) > REPEAT_AFTER_MS;
    lastSeenMs = now;

    if (isNew || stale) {
      currentUid = id;
      lastReportMs = now;
      String name = (uidLen == 7) ? readNdefText() : "";  // 7-byte UID => NTAG21x
      Serial.print("{\"t\":\"tag\",\"uid\":\"");
      Serial.print(id);
      Serial.print("\",\"len\":");
      Serial.print(uidLen);
      if (name.length()) {
        Serial.print(",\"name\":\"");
        Serial.print(name);
        Serial.print("\"");
      }
      Serial.println("}");
    }
  } else if (currentUid.length() && (now - lastSeenMs) > GONE_AFTER_MS) {
    Serial.print("{\"t\":\"gone\",\"uid\":\"");
    Serial.print(currentUid);
    Serial.println("\"}");
    currentUid = "";
  }
}
