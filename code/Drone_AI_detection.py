import cv2
from inference_sdk import InferenceHTTPClient, InferenceConfiguration
import supervision as sv

MODEL_ID = "fire-smoke-detection-zszdt-bhuqo/1"
API_KEY = "API KEY" #you can change your API Key here
CONFIDENCE_THRESHOLD = 0.4

client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key=API_KEY
).configure(InferenceConfiguration(
    api_key_transport="header"
))

box_annotator = sv.BoxAnnotator()
label_annotator = sv.LabelAnnotator()

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    raise RuntimeError("cannot open webcam.")

while True:
    ret, frame = cap.read()
    if not ret:
        print("can not read frame from webcam.")
        break

    result = client.infer(frame, model_id=MODEL_ID)

    detections = sv.Detections.from_inference(result)
    detections = detections[detections.confidence > CONFIDENCE_THRESHOLD]

    labels = [
        f"{class_name} {confidence:.2f}"
        for class_name, confidence in zip(detections["class_name"], detections.confidence)
    ]

    annotated_frame = box_annotator.annotate(scene=frame.copy(), detections=detections)
    annotated_frame = label_annotator.annotate(scene=annotated_frame, detections=detections, labels=labels)

    cv2.imshow("Fire & Smoke Detection", annotated_frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()