// Diagnostic: find a PN532 running in HSU/UART mode on unknown ESP32 pins.
//
// For each candidate (RX, TX) pair this sends the PN532 GetFirmwareVersion
// command and looks for a valid reply, so a hit is proof of a real PN532 rather
// than just electrical noise. Flash this when navi_nfc.ino reports
// "PN532 not found", then put the winning pins into navi_nfc.ino.

#include <HardwareSerial.h>

HardwareSerial probe(2);

// RX = ESP32 input, wired to the PN532's TXD. Both orders are tried because
// crossed TX/RX is the single most common wiring mistake.
static const int PAIRS[][2] = {
    {16, 17}, {17, 16}, {4, 5},   {5, 4},   {25, 26}, {26, 25},
    {32, 33}, {33, 32}, {27, 14}, {14, 27}, {12, 13}, {13, 12},
    {19, 18}, {18, 19}, {21, 22}, {22, 21}, {35, 17}, {34, 17},
    {36, 17}, {39, 17},
};
static const int NPAIRS = sizeof(PAIRS) / sizeof(PAIRS[0]);

// GetFirmwareVersion: preamble, start, LEN, LCS, TFI=D4, CMD=02, DCS, postamble
static const uint8_t GET_FW[] = {0x00, 0x00, 0xFF, 0x02, 0xFE,
                                 0xD4, 0x02, 0x2A, 0x00};

static bool probePair(int rx, int tx) {
  probe.end();
  delay(20);
  probe.begin(115200, SERIAL_8N1, rx, tx);
  delay(60);
  while (probe.available()) probe.read();

  // HSU wakeup: a run of 0x55 then padding, per the PN532 user manual.
  const uint8_t wake[] = {0x55, 0x55, 0x00, 0x00, 0x00, 0x00, 0x00,
                          0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                          0x00, 0x00};
  probe.write(wake, sizeof(wake));
  delay(20);
  probe.write(GET_FW, sizeof(GET_FW));
  probe.flush();

  uint8_t buf[64];
  int n = 0;
  unsigned long deadline = millis() + 250;
  while (millis() < deadline && n < (int)sizeof(buf)) {
    if (probe.available()) buf[n++] = probe.read();
  }
  if (n == 0) return false;

  // A real reply carries TFI 0xD5 followed by response code 0x03.
  for (int i = 0; i + 1 < n; i++) {
    if (buf[i] == 0xD5 && buf[i + 1] == 0x03) {
      Serial.printf("RX=%-2d TX=%-2d  *** PN532 FOUND ***", rx, tx);
      if (i + 4 < n) {
        Serial.printf("  IC=0x%02X firmware %d.%d", buf[i + 2], buf[i + 3],
                      buf[i + 4]);
      }
      Serial.println();
      return true;
    }
  }

  Serial.printf("RX=%-2d TX=%-2d  %d byte(s), no PN532 reply:", rx, tx, n);
  for (int i = 0; i < n && i < 12; i++) Serial.printf(" %02X", buf[i]);
  Serial.println();
  return false;
}

void setup() {
  Serial.begin(115200);
  delay(600);
  Serial.println();
  Serial.println("=== PN532 HSU scan (115200 baud on each pin pair) ===");

  int hits = 0;
  for (int i = 0; i < NPAIRS; i++) {
    if (probePair(PAIRS[i][0], PAIRS[i][1])) hits++;
  }

  Serial.printf("=== scan done, %d hit(s) ===\n", hits);
  if (!hits) {
    Serial.println("No PN532 answered on any pair. Check that it has 3V3 and GND,");
    Serial.println("that DIP switches are set to HSU (both OFF), and that TXD/RXD");
    Serial.println("actually run to this ESP32.");
  }
}

void loop() { delay(10000); }
