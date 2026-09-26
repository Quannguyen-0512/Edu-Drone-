import os
# Phải đặt TRƯỚC khi import inference: CHỈ cho phép chạy GPU
os.environ["ONNXRUNTIME_EXECUTION_PROVIDERS"] = "[CUDAExecutionProvider]"

import torch  # import TRƯỚC để nạp CUDA/cuDNN của torch, onnxruntime dùng chung
import time
import cv2
import onnxruntime as ort
import supervision as sv
from inference import get_model

# ---- Cấu hình ----
MODEL_ID = "fire-smoke-detection-zszdt-bhuqo/1"
API_KEY = ""ROBOFLOW_API_KEY""
CONFIDENCE_THRESHOLD = 0.4
# ------------------


def check_gpu(model):
    print("torch:", torch.__version__, "| CUDA:", torch.cuda.is_available())
    print("onnxruntime:", ort.__version__, "| hỗ trợ:", ort.get_available_providers())
    session = getattr(model, "onnx_session", None)
    if session is None:
        raise RuntimeError("Không đọc được session của model.")
    used = session.get_providers()
    print("Model đang dùng:", used)
    if not used or used[0] != "CUDAExecutionProvider":
        raise RuntimeError("❌ Model KHÔNG chạy trên GPU. Xem lỗi CUDA/cuDNN ở trên.")
    print(f"✅ Đang chạy trên GPU: {torch.cuda.get_device_name(0)}")


def main():
    print("Đang tải model (lần đầu cần internet, các lần sau chạy offline)...")
    model = get_model(model_id=MODEL_ID, api_key=API_KEY)
    check_gpu(model)

    box_annotator = sv.BoxAnnotator()
    label_annotator = sv.LabelAnnotator()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Không mở được webcam.")

    print("Đang chạy... nhấn 'q' để thoát.")
    prev_time = time.time()
    fps = 0.0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Không đọc được frame từ webcam.")
            break

        results = model.infer(frame, confidence=CONFIDENCE_THRESHOLD)[0]
        detections = sv.Detections.from_inference(results)

        labels = [
            f"{name} {conf:.2f}"
            for name, conf in zip(detections["class_name"], detections.confidence)
        ]

        annotated = box_annotator.annotate(scene=frame.copy(), detections=detections)
        annotated = label_annotator.annotate(scene=annotated, detections=detections, labels=labels)

        # FPS (làm mượt để số không nhảy lung tung)
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