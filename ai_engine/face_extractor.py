import os
import time
import cv2
from ultralytics import YOLO
from config import MODEL_PATH


def extract_face_with_yolo(video_path: str, id: str) -> str or None:
    """
    Scans a video using YOLO to detect the first high-quality human face,
    crops it, saves it to disk, and returns the path.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ [Extract Face] Failed to open video: {video_path}")
        return None

    # Load the exact YOLO model used in the main pipeline
    model = YOLO(MODEL_PATH)

    face_crop_path = None

    # Iterate through frames to find the first clear face
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Run YOLO inference on the frame
        results = model(frame, verbose=False)
        for r in results:
            if r.boxes is not None and len(r.boxes) > 0:
                boxes = r.boxes.xyxy.int().cpu().numpy()
                classes = r.boxes.cls.int().cpu().numpy()

                for box, cls in zip(boxes, classes):
                    class_name = model.names[cls]

                    # Look specifically for human faces
                    if class_name == "human-face":
                        x1, y1, x2, y2 = map(int, box)

                        # Add a 10-pixel safety padding around the crop
                        face_crop = frame[max(0, y1 - 10):y2 + 10, max(0, x1 - 10):x2 + 10].copy()

                        # Save only if the crop contains actual image data
                        if face_crop.size > 0:
                            os.makedirs("media/persons", exist_ok=True)
                            face_crop_path = f"media/persons/{id}.jpg"
                            cv2.imwrite(face_crop_path, face_crop)

                            cap.release()
                            return face_crop_path

    # Clean up and close the video if no face was found
    cap.release()
    return None