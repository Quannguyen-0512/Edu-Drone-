"""
Fire & Smoke Detection (GPU) - Rapid Scout ground station

Runs a YOLOv11 fire/smoke detection model from Roboflow Universe on a
live video source, using the GPU through ONNX Runtime (CUDA).

Setup:
    - Set your Roboflow API key as an environment variable:
        Windows (PowerShell):  setx ROBOFLOW_API_KEY "your_key_here"
    - Press 'q' in the video window to quit.
"""

import os
# Must be set BEFORE importing `inference`: only allow the model to run on the GPU
os.environ["ONNXRUNTIME_EXECUTION_PROVIDERS"] = "[CUDAExecutionProvider]"

import torch  # import FIRST so ONNX Runtime reuses PyTorch's CUDA/cuDNN libraries
import time
import cv2
import onnxruntime as ort
import supervision as sv
from inference import get_model

# ---- Configuration ----
MODEL_ID = "fire-smoke-detection-zszdt-bhuqo/1"
API_KEY = os.getenv("ROBOFLOW_API_KEY")  # never hard-code the key
CONFIDENCE_THRESHOLD = 0.4               # keep detections with confidence >= 0.4
VIDEO_SOURCE = 0                         # 0 = laptop webcam; use the ESP32-CAM stream URL on the drone
# -----------------------


def check_gpu(model):
    """Make sure the model is really running on the GPU, not silently falling back to the CPU."""
    print("torch:", torch.__version__, "| CUDA:", torch.cuda.is_available())
    print("onnxruntime:", ort.__version__, "| available:", ort.get_available_providers())

    session = getattr(model, "onnx_session", None)
    if session is None:
        raise RuntimeError("Could not access the model's ONNX session.")

    used = session.get_providers()
    print("Model is using:", used)
    if not used or used[0] != "CUDAExecutionProvider":
        raise RuntimeError("Model is NOT running on the GPU. Check the CUDA/cuDNN errors above.")

    print(f"Running on GPU: {torch.cuda.get_device_name(0)}")


def main():
    if not API_KEY:
        raise RuntimeError("ROBOFLOW_API_KEY environment variable is not set.")

    print("Loading model (internet needed the first time, offline afterwards)...")
    model = get_model(model_id=MODEL_ID, api_key=API_KEY)
    check_gpu(model)

    # Tools for drawing bounding boxes and labels on each frame
    box_annotator = sv.BoxAnnotator()
    label_annotator = sv.LabelAnnotator()

    cap = cv2.VideoCapture(VIDEO_SOURCE)
    if not cap.isOpened():
        raise RuntimeError("Could not open the video source.")

    print("Running... press 'q' to quit.")
    prev_time = time.time()
    fps = 0.0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Could not read a frame from the video source.")
            break

        # Run fire/smoke detection on the GPU
        results = model.infer(frame, confidence=CONFIDENCE_THRESHOLD)[0]
        detections = sv.Detections.from_inference(results)

        # Label format: "<class> <confidence>", e.g. "fire 0.87"
        labels = [
            f"{name} {conf:.2f}"
            for name, conf in zip(detections["class_name"], detections.confidence)
        ]

        # Draw on a copy so the original frame stays untouched
        annotated = box_annotator.annotate(scene=frame.copy(), detections=detections)
        annotated = label_annotator.annotate(scene=annotated, detections=detections, labels=labels)

        # FPS with an exponential moving average so the number doesn't jump around
        now = time.time()
        fps = 0.9 * fps + 0.1 * (1.0 / max(now - prev_time, 1e-6))
        prev_time = now
        cv2.putText(annotated, f"FPS: {fps:.1f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        cv2.imshow("Fire & Smoke Detection (GPU)", annotated)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
