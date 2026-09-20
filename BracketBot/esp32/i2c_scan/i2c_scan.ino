// Diagnostic: find the PN532 on the ESP32's pins.
//
// Tries every plausible SDA/SCL pair (both orders) and reports anything that
// answers. A PN532 in I2C mode sits at 0x24. Flash this when navi_nfc.ino says
// "PN532 not found", then set the pins it reports in navi_nfc.ino.

#include <Wire.h>

// Pairs worth trying: the Arduino default first, then common breakout pinouts.
static const int PAIRS[][2] = {
    {21, 22}, {22, 21}, {4, 5},   {5, 4},   {16, 17}, {17, 16},
    {18, 19}, {19, 18}, {32, 33}, {33, 32}, {25, 26}, {26, 25},
    {13, 14}, {14, 13}, {26, 27}, {27, 26}, {23, 19}, {15, 2},
};
static const int NPAIRS = sizeof(PAIRS) / sizeof(PAIRS[0]);

void scanPair(int sda, int scl) {
  Wire.end();
  delay(20);
  if (!Wire.begin(sda, scl, 100000)) {
    Serial.printf("SDA=%-2d SCL=%-2d  bus init failed\n", sda, scl);
    return;
  }

  int found = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      if (!found) Serial.printf("SDA=%-2d SCL=%-2d  FOUND:", sda, scl);
      Serial.printf(" 0x%02X%s", addr, addr == 0x24 ? "(PN532!)" : "");
      found++;
    }
  }
  if (found) Serial.println();
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println();
  Serial.println("=== ESP32 I2C scan: looking for a PN532 at 0x24 ===");

  for (int i = 0; i < NPAIRS; i++) scanPair(PAIRS[i][0], PAIRS[i][1]);

  Serial.println("=== scan done ===");
  Serial.println("Nothing at 0x24 means the PN532 is not on I2C: check that the");
  Serial.println("breakout's DIP switches are set to I2C (1=OFF 2=ON), that it has");
  Serial.println("3V3 and GND, and that it is wired to this ESP32 at all.");
}

void loop() { delay(10000); }
