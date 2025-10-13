/*
  DOIT ESP32 DEVKIT V1 (ESP32-WROOM-32)

  Flow sensor: CF-B10 => F = 7.5 * Q - 4  (±2%)
  => Q (L/min) = (F_hz + 4) / 7.5


  BLE device name: FLOW_LOGGER_000

  PREVIOSLY BEGAN TO INTEGRATE PRESSURE AND TEMPERATURE SENSORS BUT LEFT INCOMPLETE
  CALIBRATED TO DIGITEN CF-B10 FLOW RATE SENSORS.
*/

#include <NimBLEDevice.h>
#include <math.h>
#include <Preferences.h>
#include <string.h>

// ===================== USER CONFIG =====================
const uint8_t flowSensorPin = 4;   // Flow input pin
const uint8_t pressurePin   = 34;  // ADC1 channel (input-only)
const uint8_t tempPin       = 35;  // ADC1 channel (input-only)

// Pressure sensor supply (for transfer function)
const float Vs = 5.0f;            

// Voltage divider ratio to reconstruct sensorVoltage from ADC pin voltage.
// VDIV_RATIO = (Rtop + Rbottom) / Rbottom. Set to 1.0 if no divider.
const float VDIV_RATIO = 1.0f;     // <-- PUT YOUR REAL RATIO HERE (or 1.0f if none)

// Thermistor constants
const float V_IN    = 3.3f;        // ESP32 ADC reference/supply
const float R_FIXED = 10000.0f;    // Series resistor in NTC divider (Ω)
const float R0      = 3000.0f;     // NTC resistance @ 25°C (Ω)
const float BETA    = 3950.0f;     // Beta value

// ---------- Flow conversion + calibration (CF-B10) ----------
// F = K * Q + OFFSET  =>  K = 7.5 Hz/(L/min), OFFSET = -4 Hz
const float FLOW_K          = 7.5f;
const float FLOW_F_OFFSET   = -4.0f;         // Hz, in F = K*Q + OFFSET
const float FLOW_CAL_SCALE  = 0.9500000f;     // calibration factor
const float FLOW_CAL_OFFSET = 0.0f;          // L/min offset, usually 0
// ============================================================

// BLE UUIDs (custom but stable)
#define SERVICE_UUID  "12345678-0000-1000-8000-00805f9b34fb"
#define FLOW_UUID     "12345678-0001-1000-8000-00805f9b34fb"
#define TOTAL_UUID    "12345678-0002-1000-8000-00805f9b34fb"
#define TEMP_UUID     "12345678-0003-1000-8000-00805f9b34fb"
#define PRESSURE_UUID "12345678-0004-1000-8000-00805f9b34fb"

NimBLECharacteristic *pFlowChar, *pTotalChar, *pTempChar, *pPressureChar;
Preferences prefs;

// Flow accumulators
volatile uint32_t pulseCount = 0;
volatile uint32_t lastPulseMicros = 0;               // ISR debounce timebase
const uint32_t PULSE_DEBOUNCE_US = 1500;             // 1.5 ms; raise if needed

float flowRate = 0.0f;                               // L/min (current)
float totalLiters = 0.0f;                            // Totalized liters
unsigned long previousMillis = 0;

// Zero-flow handling
const float ZERO_DEADBAND_LPM = 0.25f;               // clamp small values to 0
const uint8_t MIN_PULSES = 2;                        // ignore tiny counts as noise

// ---------- ISR: Count pulses with a short guard against spurious edges ----------
void IRAM_ATTR pulseCounter() {
  uint32_t now = micros();
  if (now - lastPulseMicros >= PULSE_DEBOUNCE_US) {
    pulseCount++;
    lastPulseMicros = now;
  }
}

// ---------- Simple ADC averaging ----------
static inline uint16_t readADC(uint8_t pin, uint8_t samples = 16) {
  uint32_t acc = 0;
  for (uint8_t i = 0; i < samples; i++) acc += analogRead(pin);
  return acc / samples;
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("Booting ESP32 DEVKIT V1 - Flow");

  // ADC config (ESP32 classic)
  analogReadResolution(12); // 0..4095
  analogSetPinAttenuation(pressurePin, ADC_11db); // ~0-3.3 V
  analogSetPinAttenuation(tempPin,     ADC_11db);

  // Flow input: external 10k pull-up to 3.3V recommended
  pinMode(flowSensorPin, INPUT);
  attachInterrupt(digitalPinToInterrupt(flowSensorPin), pulseCounter, RISING);

  // Persisted totalizer
  prefs.begin("flowlog", false);
  totalLiters = prefs.getFloat("totalL", 0.0f);

  // ---------- BLE setup ----------
  NimBLEDevice::init("FLOW_LOGGER_000");  // device name shown in scanner apps
  NimBLEServer* pServer = NimBLEDevice::createServer();
  NimBLEService* pService = pServer->createService(SERVICE_UUID);

  pFlowChar     = pService->createCharacteristic(FLOW_UUID,     NIMBLE_PROPERTY::NOTIFY);
  pTotalChar    = pService->createCharacteristic(TOTAL_UUID,    NIMBLE_PROPERTY::NOTIFY);
  pTempChar     = pService->createCharacteristic(TEMP_UUID,     NIMBLE_PROPERTY::NOTIFY);
  pPressureChar = pService->createCharacteristic(PRESSURE_UUID, NIMBLE_PROPERTY::NOTIFY);

  // Add human-readable labels (Characteristic User Description, UUID 0x2901)
  pFlowChar->createDescriptor("2901")->setValue("Flow (L/min)");
  pTotalChar->createDescriptor("2901")->setValue("Total (L)");
  pTempChar->createDescriptor("2901")->setValue("Temperature (C)");
  pPressureChar->createDescriptor("2901")->setValue("Pressure (kPa)");

  pService->start();

  // --- Version-safe advertising data (no setScanResponse(bool)) ---
  NimBLEAdvertising* pAdvertising = NimBLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);

  NimBLEAdvertisementData advData;
  advData.setName("FLOW_LOGGER_000");                   // show device name
  advData.setCompleteServices(NimBLEUUID(SERVICE_UUID));// advertise the service
  pAdvertising->setAdvertisementData(advData);

  // Optional: also put the name in scan response (works across NimBLE versions)
  NimBLEAdvertisementData scanData;
  scanData.setName("FLOW_LOGGER_000");
  pAdvertising->setScanResponseData(scanData);

  pAdvertising->start();

  Serial.println("BLE Initialized as 'FLOW_LOGGER_000'");
  Serial.print("Bluetooth MAC: ");
  Serial.println(NimBLEDevice::getAddress().toString().c_str());

  previousMillis = millis();
}

void loop() {
  unsigned long currentMillis = millis();

  // Run once per ~second 
  if (currentMillis - previousMillis >= 1000) {
    unsigned long dt_ms = currentMillis - previousMillis;
    previousMillis = currentMillis;
    float dt_s = dt_ms / 1000.0f;

    // ---------- FLOW (CF-B10 formula + calibration) ----------
    noInterrupts();
    uint32_t count = pulseCount;  // pulses in last dt_s
    pulseCount = 0;
    interrupts();

    float F_hz = (dt_s > 0.0f) ? (count / dt_s) : 0.0f;

    // Suppress tiny measured frequencies so the -4 Hz intercept doesn't imply fake flow
    if (F_hz < 1.0f) {  // adjust as needed
      F_hz = 0.0f;
    }

    float Q_Lpm = 0.0f;
    if (count >= MIN_PULSES) {
      // CF-B10 base conversion: F = K*Q + OFFSET  => Q = (F - OFFSET) / K
      float baseQ = (F_hz - FLOW_F_OFFSET) / FLOW_K;    // == (F_hz + 4) / 7.5

      // Apply calibration
      float calQ = baseQ * FLOW_CAL_SCALE + FLOW_CAL_OFFSET;

      // Zero deadband AFTER calibration
      Q_Lpm = (calQ < ZERO_DEADBAND_LPM) ? 0.0f : calQ;
    } else {
      Q_Lpm = 0.0f; // ignore tiny counts as noise
    }

    flowRate = Q_Lpm;
    float litersThisInterval = Q_Lpm * dt_s / 60.0f;  // L/min * s -> L
    totalLiters += litersThisInterval;

    // Persist total every ~10 seconds
    static uint8_t persistTick = 0;
    if (++persistTick >= 10) {
      persistTick = 0;
      prefs.putFloat("totalL", totalLiters);
    }

    // ---------- PRESSURE ----------
    uint16_t rawPressure = readADC(pressurePin, 16);
    float vOut_adc = (rawPressure / 4095.0f) * V_IN;   // voltage at ESP32 pin
    float sensorVoltage = vOut_adc * VDIV_RATIO;       // reconstruct sensor output

    // Transfer Function: Vo = ((P * 0.0045726) – 0.011453) * Vs
    // => P (kPa) = ((Vo/Vs) + 0.011453) / 0.0045726
    float pressure_kPa = ((sensorVoltage / Vs) + 0.011453f) / 0.0045726f;

    // ---------- TEMPERATURE (NTC Beta) ----------
    uint16_t rawTemp = readADC(tempPin, 16);
    float vTemp = (rawTemp / 4095.0f) * V_IN;
    float tempC = NAN;
    if (vTemp > 0.0f && vTemp < V_IN) {
      float rNTC = (vTemp * R_FIXED) / (V_IN - vTemp);
      float invT = (1.0f / 298.15f) + (logf(rNTC / R0) / BETA);
      float tempK = 1.0f / invT;
      tempC = tempK - 273.15f;
    }

    // ---------- Serial Output ----------
    Serial.print("Flow: ");
    Serial.print(flowRate, 2);
    Serial.print(" L/min  | Total: ");
    Serial.print(totalLiters, 3);
    Serial.print(" L  | Pressure: ");
    Serial.print(pressure_kPa, 2);
    Serial.print(" kPa  | Temp: ");
    if (isnan(tempC)) Serial.print("NA");
    else Serial.print(tempC, 2);
    Serial.println(" °C");

    // ---------- BLE Notify (as strings) ----------
    char flowStr[16], totalStr[16], tempStr[16], pressureStr[16];
    dtostrf(flowRate,     4, 2, flowStr);
    dtostrf(totalLiters,  6, 3, totalStr);
    if (isnan(tempC)) strcpy(tempStr, "NA");
    else dtostrf(tempC,   4, 2, tempStr);
    dtostrf(pressure_kPa, 6, 2, pressureStr);

    if (pFlowChar)     { pFlowChar->setValue(flowStr);         pFlowChar->notify(); }
    if (pTotalChar)    { pTotalChar->setValue(totalStr);       pTotalChar->notify(); }
    if (pTempChar)     { pTempChar->setValue(tempStr);         pTempChar->notify(); }
    if (pPressureChar) { pPressureChar->setValue(pressureStr); pPressureChar->notify(); }
  }
}
