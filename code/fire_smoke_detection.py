import os
# Must be set BEFORE importing inference: allow the GPU provider ONLY
os.environ["ONNXRUNTIME_EXECUTION_PROVIDERS"] = "[CUDAExecutionProvider]"

import torch  # import first so onnxruntime shares torch's CUDA/cuDNN
import time
from collections import Counter

import cv2
import numpy as np
import onnxruntime as ort
import supervision as sv
import websocket
from inference import get_model

try:
    import winsound  # alert sound, Windows only
except ImportError:
    winsound = None

# ---- Model configuration ----
MODEL_ID = "fire-smoke-detection-yolov11/2"   # detection model with 2 classes: Fire, Smoke
API_KEY = os.getenv("ROBOFLOW_API_KEY")       # read the API key from an environment variable
CONFIDENCE_THRESHOLD = 0.25                   # general threshold, filtered further by the per-class thresholds

# ---- Video source ----
VIDEO_MODE = "websocket"  # "websocket" = ESP32 board + webcam; "webcam" = webcam plugged into the laptop
CAMERA_WS_URL = os.getenv("CAMERA_WS_URL", "ws://192.168.4.1/camera_ws")  # WebSocket address of the ESP32 board (set the CAMERA_WS_URL environment variable to override)
WS_TIMEOUT = 5                                # maximum seconds to wait for each frame
WEBCAM_INDEX = 0                              # webcam index when using "webcam" mode

# ---- Per-class thresholds ----
CLASS_THRESHOLDS = {"fire": 0.35, "smoke": 0.3}
DEFAULT_CLASS_THRESHOLD = 0.6

# ---- Alert configuration ----
ALERT_MIN_FRAMES = 3   # consecutive frames with fire/smoke before the alert turns on
ALERT_HOLD_SEC = 1.5   # keep the alert on after the last detection (seconds)
FLASH_PERIOD = 0.5     # red flash period (seconds)
BEEP_COOLDOWN = 1.0    # minimum gap between two beeps (seconds)

DEBUG = False  # True = print the model's results before filtering


def check_gpu(model):
    """Check that the model is really running on the GPU."""
    print("torch:", torch.__version__, "| CUDA:", torch.cuda.is_available())
    print("onnxruntime:", ort.__version__, "| supported:", ort.get_available_providers())
    session = getattr(model, "onnx_session", None)
    if session is None:
        raise RuntimeError("Could not read the model's session.")
    used = session.get_providers()
    print("Model is using:", used)
    if not used or used[0] != "CUDAExecutionProvider":
        raise RuntimeError("Model is NOT running on the GPU.")
    print(f"Running on GPU: {torch.cuda.get_device_name(0)}")


def connect_websocket():
    """Connect to the ESP32 board over WebSocket, retrying until it works."""
    while True:
        try:
            print("Connecting to ESP32 + webcam:", CAMERA_WS_URL)
            ws = websocket.create_connection(CAMERA_WS_URL, timeout=WS_TIMEOUT)
            print("Connected to ESP32 + webcam.")
            return ws
        except Exception as e:
            print("Connection failed:", e, "| retrying in 2 seconds...")
            time.sleep(2)


def read_ws_frame(ws):
    """Receive one JPEG frame over WebSocket and decode it into an OpenCV image."""
    data = ws.recv()
    if isinstance(data, str):  # ignore text messages, only image data is used
        return None
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)


def filter_by_class(detections):
    """Keep only the detections that pass each class's own threshold."""
    if len(detections) == 0:
        return detections
    keep = np.array([
        conf >= CLASS_THRESHOLDS.get(str(name).lower(), DEFAULT_CLASS_THRESHOLD)
        for name, conf in zip(detections["class_name"], detections.confidence)
    ], dtype=bool)
    return detections[keep]


def draw_alert(frame, now):
    """Red overlay, red border, and warning text, flashing every FLASH_PERIOD."""
    h, w = frame.shape[:2]
    if int(now / (FLASH_PERIOD / 2)) % 2 == 0:
        red = frame.copy()
        red[:] = (0, 0, 255)  # OpenCV uses BGR color order
        frame = cv2.addWeighted(red, 0.35, frame, 0.65, 0)
        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), (0, 0, 255), 10)

    text = "FIRE / SMOKE DETECTED!"
    scale = 0.8 if w < 800 else 1.1  # smaller text for small frames
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
    x, y = (w - tw) // 2, h - 20
    cv2.rectangle(frame, (x - 10, y - th - 10), (x + tw + 10, y + 10), (0, 0, 0), -1)
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 255), 2)
    return frame


def main():
    if not API_KEY:
        raise RuntimeError("The ROBOFLOW_API_KEY environment variable is not set.")

    print("Loading the model (needs internet the first time, runs offline afterwards)...")
    model = get_model(model_id=MODEL_ID, api_key=API_KEY)
    check_gpu(model)

    box_annotator = sv.BoxAnnotator()
    label_annotator = sv.LabelAnnotator()

    # ---- Open the video source ----
    ws, cap = None, None
    if VIDEO_MODE == "websocket":
        ws = connect_websocket()
    else:
        cap = cv2.VideoCapture(WEBCAM_INDEX)
        if not cap.isOpened():
            raise RuntimeError("Could not open the webcam.")

    print("Running... press 'q' to quit, 't' to toggle a test alert.")
    prev_time = time.time()
    fps = 0.0
    fire_streak = 0                 # consecutive frames with fire/smoke
    last_fire_time = float("-inf")  # last time the alert condition was met
    last_beep = 0.0
    test_alert = False              # test alert mode, toggled with the 't' key
    class_counter = Counter()       # counts how often each class was detected

    while True:
        # ---- Read a frame ----
        if ws is not None:
            try:
                frame = read_ws_frame(ws)
            except Exception as e:  # connection lost or timed out
                print("Camera connection lost:", e)
                ws.close()
                ws = connect_websocket()
                continue
        else:
            ret, frame = cap.read()
            if not ret:
                print("Could not read a frame from the webcam.")
                break
        if frame is None:
            continue

        # ---- Detection ----
        results = model.infer(frame, confidence=CONFIDENCE_THRESHOLD)[0]
        raw = sv.Detections.from_inference(results)
        if DEBUG and len(raw) > 0:
            print("Before filtering:", list(zip(raw["class_name"], raw.confidence.round(2))))
        detections = filter_by_class(raw)
        class_counter.update(detections["class_name"])

        labels = [
            f"{name} {conf:.2f}"
            for name, conf in zip(detections["class_name"], detections.confidence)
        ]
        annotated = box_annotator.annotate(scene=frame.copy(), detections=detections)
        annotated = label_annotator.annotate(scene=annotated, detections=detections, labels=labels)

        now = time.time()

        # ---- Alert logic ----
        fire_streak = fire_streak + 1 if len(detections) > 0 else 0
        if fire_streak >= ALERT_MIN_FRAMES:
            last_fire_time = now
        alert_on = test_alert or (now - last_fire_time) <= ALERT_HOLD_SEC

        if alert_on:
            annotated = draw_alert(annotated, now)
            if winsound and now - last_beep >= BEEP_COOLDOWN:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                last_beep = now

        # ---- FPS (exponential moving average) ----
        fps = 0.9 * fps + 0.1 * (1.0 / max(now - prev_time, 1e-6))
        prev_time = now
        cv2.putText(annotated, f"FPS: {fps:.1f}", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        cv2.imshow("Fire & Smoke Detection (GPU)", annotated)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("t"):
            test_alert = not test_alert
            print("Test alert:", "ON" if test_alert else "OFF")

    # ---- Clean up ----
    if ws is not None:
        ws.close()
    if cap is not None:
        cap.release()
    cv2.destroyAllWindows()
    print("Detections per class:", dict(class_counter))


if __name__ == "__main__":
    main()
