# Edudrone: Build Log

A build log of an open-hardware FPV drone, from a first 5 inch build to RapidScout, a drone I am building to help spot smoke and fire from the air.

## At a glance

| | |
|---|---|
| **What it is** | A build log and code for an open-hardware FPV drone that I assembled from individual parts so every component can be opened up and explained, and for its next stage, RapidScout, a low cost scouting drone that I am building to spot fire and smoke. |
| **What it does** | A USB camera on an ESP32-S3 board sends video to a laptop, which runs a [public YOLO fire and smoke detection model](https://universe.roboflow.com/sayed-gamall/fire-smoke-detection-yolov11) on its GPU and raises an alert. The plan is to carry the camera on the drone. For now it runs on the bench and is not mounted on the drone yet. Planned next: tag each detection with a GPS position and fly a pre-mapped route. The drone only reports, it does not act on its own. |
| **Built with** | A [7 inch long range frame](#the-7-inch-build), a GEPRC Taker H743 BT flight controller ([manual](docs/TAKER-H743-BT-FC-Manual.pdf)) running INAV, a GEPRC GEP-M10Q GPS, an ExpressLRS radio link, a USB camera on an ESP32-S3 that [streams video over WebSocket](#camera-and-ai-detection-over-websocket) (so far on the bench, not yet mounted on the drone), and a laptop with an NVIDIA RTX 3050 GPU running Python with ONNX Runtime and Roboflow Inference. |
| **The code** | One Python program, [`code/fire_smoke_detection.py`](code/fire_smoke_detection.py). It receives JPEG frames from the ESP32 over WebSocket, runs the Roboflow fire and smoke model on the GPU with ONNX Runtime, applies a separate confidence threshold to each class, draws boxes and a frame rate counter, and raises a flashing red alert after 3 detections in a row. It checks that the model really runs on the GPU, reconnects by itself when the video drops, and can use the laptop's webcam for testing. |
| **My role** | Chose the parts, soldered the electronics, flashed and configured the flight controller, rebuilt the drone on a 7 inch frame after an ESC failure, and wrote the detection program. I did not train the detection model, it is a public one. |
| **Status** | Work in progress. The 7 inch drone is built. Video streaming and fire and smoke detection work on the laptop, tested with the camera on the bench. The camera and ESP32-S3 are not mounted on the drone yet, so the video link has not been tested in flight. Reading GPS data to tag detections is [in progress](#currently-working-on). Flying a pre-mapped route and a ground station screen are not done yet. |
| **In this repo** | The build log below ([Phase 1](#phase-1-edudrone---how-i-chose-my-setup) is the 5 inch Edudrone, [Phase 2](#phase-2-rapidscout---giving-the-drone-a-mission) is RapidScout), the detection program in [`code/`](code/), a hardware diagram and screenshots in [`images/`](images/), and the flight controller manual in [`docs/`](docs/). |
## Phase 1: Edudrone - How I Chose My Setup

### Choosing a Drone Class: Microdrone, Freestyle, or Long Range

FPV drones are usually grouped by propeller size, and that size roughly decides what the drone is good at.

A microdrone, or whoop, runs 1 to 2 inch propellers. It's small, light, safe to fly indoors, and forgiving for someone just learning the sticks.

A freestyle drone runs 5 inch propellers, sometimes 4 or 6 inch. This is the class most people picture when they think FPV: fast, agile, built for tricks and tight maneuvering.

A long range drone runs 7 inch propellers or bigger. Bigger props move more air per rotation, so the drone trades some agility for efficiency and flight time, which is what long range is actually for.

Edudrone started as a freestyle build, 5 inch propellers, and only later moved toward long range once the mission changed.

### Practice Phase: Meteor65 Pro

Before committing to real parts, I bought a Meteor65 Pro and a RadioMaster controller, not to fly for fun but to practice the fundamentals: flashing firmware onto a flight controller, binding a receiver to a transmitter, basic tuning.

I got the version without a camera and VTX, since I wanted to practice flying and tuning rather than FPV racing. If you're using a RadioMaster 2.4GHz ELRS controller like I am, pick the ELRS 2.4G RX version.

### Core Hardware: What Are ESC and FC

Before picking parts, it helps to know what a 5 inch drone actually needs underneath.

The ESC, or Electronic Speed Controller, usually comes as a "4-in-1" board that controls all four motors' speed based on signals from the flight controller.

The FC, or Flight Controller, is the brain. It runs firmware like INAV, Betaflight, or ArduPilot, reads data from the gyroscope, accelerometer, GPS, and compass, and sends output commands to the ESC.

### What I Actually Chose (5 inch build)

Stack: GEPRC Taker H743BT flight controller. The ESC was originally the stock one bundled with the stack, but I later replaced it with a Flywoo GOKU G55M 55A 4-in-1 ESC after solder damage (more on that below).

Motor: AxisFlying 1960KV.

Receiver: GEPRC ELRS.

GPS module: GEPRC GEP-M10Q

### Soldering: Temperature and Technique

The cheap soldering iron I first bought from the market couldn't get solder to flow evenly onto a pad no matter what I tried. I switched to an FNIRSI HS-01 (the HS-02 has more features if you want them), and while I was still getting used to the new iron, I ruined my first ESC: solder smeared around the board instead of sitting cleanly on the pad. That mistake also took out my GPS module and receiver, damaged by the same bad soldering job.

Motor pads need around 350°C, ESC pads around 400°C. Pre-tin the wire and the pad separately, apply flux first, and use 63/37 solder since it sets fast and leaves fewer cold joints.

I ended up replacing the damaged ESC with a Flywoo GOKU G55M 55A 4-in-1, which has a pad-hole design that makes soldering noticeably easier than the stock board.

One small trick: if a motor spins the wrong direction, you can reverse it by swapping any two of the three motor-to-ESC wires, no need to re-flash anything.

Safety tip: always route the first battery plug-in after soldering through a smoke stopper. If there's a short, you'll know before anything burns.

### Flashing Firmware: Starting with Betaflight, Then Switching to INAV

Flashing firmware on the GEPRC Taker H743BT works the same whether you're using Betaflight or INAV. Here's the process I followed:

1. Open the Board & Build tab in the firmware flasher and select the exact target, GEPRC_TAKER_H743. It shows a "Community/Manufacturer supported, not officially supported" warning, which is normal for this board.
2. In Build Configuration, set Radio Protocol to CRSF and Motor Protocol to DSHOT.
3. Match the other options (GPS, Optical Flow, Pin IO, Range Finder, VTX) to your actual hardware.
4. Go to the Flash tab, choose Load Firmware [Online], then Flash Firmware.
5. Verify the flash worked by checking gyro and accelerometer response in the Setup tab.

I flashed Betaflight first, then flashed INAV onto the same board using the exact same steps.

Betaflight doesn't have Position Hold mode, by design, since it's built for manual, freestyle, and racing flight. INAV does have it. Since RapidScout needs the drone to hold a stable position over a target, switching to INAV wasn't optional. It was a requirement, not just curiosity about trying a different firmware.

### FC Setup: Receiver and GPS

On the Receiver tab, set Receiver Mode to Serial (via UART), Serial Receiver Provider to CRSF, and enable Serial RX on UART2. My receiver is a GEPRC ELRS, which needs an ELRS 2.4GHz transmitter to bind to.

For GPS, connect it to UART4, set Sensor Input to GPS, and set the baud rate to 115200.

[![Board with GPS mounted, receiver not yet installed](https://github.com/Quannguyen-0512/Edu-Drone-/raw/main/images/gps-setup.png)](/Quannguyen-0512/Edu-Drone-/blob/main/images/gps-setup.png)

### First Test Flight and Tuning

If you're used to the gentle
