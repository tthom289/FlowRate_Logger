# FlowRate_Logger

Coolant flow rate logger for FCEV & BEV thermal validation. Uses low-cost Digiten sensors with ESP32 to transmit data via BLE to a Python client for real-time visualization and logging. Ideal for testing and optimizing EV thermal management systems.

## Hardware Components

### Digiten Flow Sensor

**Model:** G1" Male Thread Water Flow Hall Sensor Switch Flowmeter Counter 2-50L/min

#### Specifications

- **Working range:** 2-50L/min
- **Max water pressure:** 1.75Mpa
- **Formula:** F=7.5Q-4(L/min)
- **Working voltage range:** DC5-15V
- **Accuracy:** ±3%
- **Temperature resistance:** 80℃
- **Female thread external diameter:** 32.6mm (1.28")
- **Tube length:** 60mm (2.36")
- **Cable length:** 30cm (11.81")
- **Dimensions (L×W×H):** 60mm × 30mm × 28mm

<img width="422" alt="Digiten Flow Sensor" src="https://github.com/user-attachments/assets/db5d647e-cf1a-4b2f-9a38-694f63f995a1">

### ESP32-DevKitC-32

<img width="610" alt="ESP32-DevKitC-32" src="https://github.com/user-attachments/assets/f14c5eee-2c36-472a-bdd4-70b2951b5931">

### 3D Printed Housing

The ESP32 module is housed in a custom 3D printed enclosure for protection and mounting.

**Download:** [ESP32-WROOM-38 Pin Enclosure on MakerWorld](https://makerworld.com/en/models/1555778-esp32-wroom-38-pin-enclosure?from=search#profileId-1634597)

![Module in 3D printed housing](https://github.com/user-attachments/assets/2acb1998-0216-4eaf-9035-5897f9b06c4f)

## Wiring Diagram

### ESP32 to Digiten Flow Sensor Connections

| Digiten Wire Color | ESP32 Pin | Function |
|-------------------|-----------|----------|
| Red               | Pin 19    | 3.3V     |
| Black             | Pin 38    | GND      |
| Yellow            | Pin 26    | GPIO 4   |

## Power Supply

For remote operation, each flow sensor is powered using a USB-C power bank. The setup uses an **onn 10,000 mAh Portable Power Bank with Built-In USB-C Cable (Model: WIABLK 36009564)**, mounted with double-sided tape.

<img width="425" alt="Power bank mounting" src="https://github.com/user-attachments/assets/115b0124-ae62-4763-ba6b-739fb24e9f79">

---

## Getting Started

### Running the Application

1. Run the flow logger Python script
2. Power on your flow meter modules
3. Click "Scan for BLE devices"

> **Note:** A filter is applied to display only BLE devices containing the name "FLOW_LOGGER_". This helps mitigate scrolling through numerous BLE devices depending on your location.

<img width="965" alt="BLE Device Scanner" src="https://github.com/user-attachments/assets/259dc252-faac-4ba0-8588-0b8e361e5166">

### Monitoring Flow Data

Once you add a device, a new window will pop up displaying:
- Live graph of flow rate
- Instantaneous flow rate
- Total coolant flow
- Minimum & maximum flow rates
- Average flow rate

You also have the option to reset these metrics.

<img width="802" alt="Flow Rate Monitor Window" src="https://github.com/user-attachments/assets/aadfb9f0-e29a-42a2-8eb2-96b4301e2d23">

### Multiple Device Support

You can reliably run up to **5 flow loggers simultaneously** before potentially encountering performance issues.

<img width="1917" alt="Multiple Flow Loggers Running" src="https://github.com/user-attachments/assets/fcd6d2e3-5bc7-43cd-b6b4-c248f2de80ad">

### Data Logging

The application includes data logging capabilities. To configure the log file location:

**Line 91 in code:**
```python
self.log_dir = r"C:\path\to\your\logs"
