# import os
# import warnings
# import time
# import collections
# import shutil
# import queue
# from datetime import datetime
# import cv2
# import threading
# import numpy as np  # Added for the background cache updater
#
# # SUPPRESS NOISE
# warnings.filterwarnings("ignore", category=DeprecationWarning)
# warnings.filterwarnings("ignore", category=FutureWarning)
# os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
# os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
#
# import tensorflow as tf
#
# try:
#     tf.config.set_visible_devices([], 'GPU')
# except Exception:
#     pass
#
# from ultralytics import YOLO
#
# from db.crud_events import log_event_start, log_event_end, create_unknown_person
# from config import MODEL_PATH, PRE_ROLL_SECONDS, EVENTS_DIR, COOLDOWN_SECONDS
# from ai_engine.face_recognition import identify_face, FaceCache
# from db.session import SessionLocal  # Added to allow the background thread to fetch new data
# from sqlalchemy import text
#
# # Define our new directory structure
# TEMP_DIR = "media/temp"
# FAMILY_DIR = os.path.join(EVENTS_DIR, "family")
# UNWANTED_DIR = os.path.join(EVENTS_DIR, "unwanted")
#
# # Ensure directories exist
# os.makedirs(TEMP_DIR, exist_ok=True)
# os.makedirs(FAMILY_DIR, exist_ok=True)
# os.makedirs(UNWANTED_DIR, exist_ok=True)
#
#
# # --- BACKGROUND DISK WRITER ---
# def disk_writer_thread(filename, fps, width, height, frame_queue):
#     """Saves frames to disk in the background so the camera NEVER drops a frame."""
#     fourcc = cv2.VideoWriter_fourcc(*'mp4v')
#     writer = cv2.VideoWriter(filename, fourcc, fps, (width, height))
#
#     while True:
#         frame = frame_queue.get()
#         if frame is None:  # None is our signal to stop recording
#             break
#         writer.write(frame)
#
#     writer.release()
#
#
# def camera_worker_process(camera_id: str, camera_name: str, video_url: str, user_id: str, user_cache: dict,
#                           alert_queue, command_queue):
#     print(f"📹 [{camera_name}] Process started. Verifying connection...")
#
#     # --- NEW: FAKE/DEAD LINK CHECK ---
#     cap = cv2.VideoCapture(video_url)
#
#     if not cap.isOpened():
#         print(f"❌ [{camera_name}] DEAD LINK! Cannot connect to {video_url}. Shutting down worker to save resources.")
#         return
#
#     # Try reading a single frame to ensure it's not a fake/empty stream
#     success, _ = cap.read()
#     if not success:
#         print(f"❌ [{camera_name}] FAKE STREAM! Connected but receiving no video data. Shutting down worker.")
#         cap.release()
#         return
#
#     # If we made it here, the link is valid and transmitting.
#     cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)
#
#     fps = cap.get(cv2.CAP_PROP_FPS)
#     if not fps or fps != fps: fps = 20.0
#
#     buffer_size = int(fps * PRE_ROLL_SECONDS)
#     frame_buffer = collections.deque(maxlen=buffer_size)
#
#     # --- NEW: BACKGROUND FRAME READER ---
#     # This prevents the camera buffer from filling up while YOLO is processing
#     camera_read_queue = queue.Queue(maxsize=int(fps * 2))  # Buffer up to 2 seconds of frames
#     stop_reader = False
#
#     def camera_reader_task():
#         while not stop_reader:
#             ret, f = cap.read()
#             if not ret:
#                 time.sleep(0.01)
#                 continue
#
#             # If our internal queue is full, drop the oldest frame to prevent latency buildup
#             if camera_read_queue.full():
#                 try:
#                     camera_read_queue.get_nowait()
#                 except queue.Empty:
#                     pass
#             camera_read_queue.put(f)
#
#     reader_thread = threading.Thread(target=camera_reader_task, daemon=True)
#     reader_thread.start()
#     # ------------------------------------
#
#     try:
#         model = YOLO(MODEL_PATH)
#         model.to('cuda:0')
#     except Exception as e:
#         print(f"❌ [CAM] YOLO Error: {e}")
#         return
#
#     # --- VIDEO RECORDING STATE ---
#     is_recording = False
#     temp_filename = ""
#     event_timestamp = ""
#     frames_since_last_seen = 0
#
#     # Queue for our background video writer
#     video_write_queue = None
#     video_thread = None
#
#     # --- AI IDENTIFICATION STATE ---
#     is_identifying = False
#     alert_sent_this_event = False
#     identity_locked = False
#
#     current_match_name = "Unknown"
#     current_match_id = None
#     current_match_type = "UNWANTED"
#
#     def face_identification_task(crop_img):
#         nonlocal is_identifying, alert_sent_this_event, identity_locked
#         nonlocal current_match_name, current_match_id, current_match_type
#
#         try:
#             name, det_id, det_type = identify_face(crop_img, user_cache)
#             current_time = datetime.now().isoformat()
#
#             if name != "Unknown":
#                 print(f"✅ [{camera_name}] AI Identified: {name} ({det_type})")
#                 current_match_name = name
#                 current_match_id = det_id
#                 current_match_type = det_type
#
#                 if det_type == "UNWANTED" and not alert_sent_this_event:
#                     alert_queue.put({
#                         "type": "alert",
#                         "user_id": user_id,
#                         "person_id": current_match_id,
#                         "camera_id": camera_id,
#                         "camera_name": camera_name,
#                         "person_name": current_match_name,
#                         "timestamp": current_time
#                     })
#                     alert_sent_this_event = True
#             else:
#                 print(f"🚨 [{camera_name}] Unknown face! Generating new profile...")
#
#                 # --- CHANGED: Unpack the ID and the new UI name ---
#                 new_pid, generated_name = create_unknown_person(user_id, crop_img)
#
#                 if new_pid:
#                     # --- CHANGED: Use the generated name instead of "Unknown_Intruder" ---
#                     current_match_name = generated_name
#                     current_match_id = new_pid
#                     current_match_type = "UNWANTED"
#
#                     # Cache the new intruder immediately for the current loop
#                     try:
#                         from deepface import DeepFace
#                         rep = DeepFace.represent(img_path=crop_img, model_name="ArcFace", enforce_detection=False)[0]
#                         user_cache[new_pid] = {
#                             "name": generated_name,  # --- CHANGED: Cache the UI name ---
#                             "type": "UNWANTED",
#                             "embedding": rep["embedding"]
#                         }
#                     except Exception as e:
#                         print(f"⚠️ Could not cache new intruder: {e}")
#
#                     if not alert_sent_this_event:
#                         alert_queue.put({
#                             "type": "alert",
#                             "user_id": user_id,
#                             "person_id": current_match_id,
#                             "camera_id": camera_id,
#                             "camera_name": camera_name,
#                             "person_name": current_match_name,
#                             "timestamp": current_time
#                         })
#                         alert_sent_this_event = True
#
#             identity_locked = True
#         except Exception as e:
#             import traceback
#             print(f"❌ [THREAD ERROR] Face ID Failed: {traceback.format_exc()}")
#         finally:
#             is_identifying = False
#
#     while True:
#         # --- NEW: IPC COMMAND QUEUE MAILBOX CHECK ---
#         try:
#             cmd = command_queue.get_nowait()
#             if cmd.get("action") == "RELOAD_FACES" and cmd.get("user_id") == user_id:
#                 print(f"🔄 [{camera_name}] RELOAD COMMAND RECEIVED! Fetching fresh faces from DB...")
#
#                 # Fetch new data using the helper from face_recognition.py
#                 new_cache = FaceCache.get_updated_user_cache(user_id)
#
#                 # Safely update the dictionary in memory
#                 user_cache.clear()
#                 user_cache.update(new_cache)
#                 print(f"✅ [{camera_name}] Memory synced instantly.")
#         except queue.Empty:
#             pass  # No messages, just proceed to read the video frame normally
#
#         # --- CHANGED: Pull from our high-speed queue instead of directly from cap ---
#         try:
#             frame = camera_read_queue.get(timeout=1.0)
#             success = True
#         except queue.Empty:
#             continue
#         # ----------------------------------------------------------------------------
#
#         frame_buffer.append(frame)
#         results = model.track(frame, persist=True, tracker="bytetrack.yaml", verbose=False, device='cuda:0')
#
#         person_in_frame = False
#         face_box = None
#
#         for r in results:
#             if r.boxes is not None and len(r.boxes) > 0:
#                 boxes = r.boxes.xyxy.int().cpu().numpy()
#                 classes = r.boxes.cls.int().cpu().numpy()
#
#                 for box, cls in zip(boxes, classes):
#                     class_name = model.names[cls]
#                     if class_name == "person":
#                         person_in_frame = True
#                     if class_name == "human-face" and face_box is None:
#                         face_box = box
#
#         # --- EVENT LOGIC ---
#         if person_in_frame:
#             frames_since_last_seen = 0
#
#             if not is_recording:
#                 # 1. START RECORDING NON-BLOCKING
#                 is_recording = True
#                 identity_locked = False
#                 alert_sent_this_event = False
#
#                 current_match_name = "Unknown"
#                 current_match_id = None
#                 current_match_type = "UNWANTED"
#
#                 event_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#                 temp_filename = os.path.join(TEMP_DIR, f"temp_{camera_id}_{event_timestamp}.mp4")
#
#                 h, w, _ = frame.shape
#
#                 # Start the background Disk Writer thread
#                 video_write_queue = queue.Queue()
#                 video_thread = threading.Thread(target=disk_writer_thread,
#                                                 args=(temp_filename, fps, w, h, video_write_queue))
#                 video_thread.start()
#
#                 # Instantly dump the pre-roll to the queue (virtually 0 delay)
#                 for b_frame in frame_buffer:
#                     video_write_queue.put(b_frame)
#
#                 print(f"🎥 [{camera_name}] Person entered. Recording dynamically to temp buffer...")
#             else:
#                 # Keep sending frames to the queue
#                 video_write_queue.put(frame)
#
#                 # 2. RUN BACKGROUND FACE HUNT
#                 if not identity_locked and not is_identifying and face_box is not None:
#                     is_identifying = True
#                     x1, y1, x2, y2 = map(int, face_box)
#                     face_crop = frame[max(0, y1 - 10):y2 + 10, max(0, x1 - 10):x2 + 10].copy()
#
#                     if face_crop.size > 0:
#                         threading.Thread(target=face_identification_task, args=(face_crop,)).start()
#                     else:
#                         is_identifying = False
#         else:
#
#             if is_recording:
#                 video_write_queue.put(frame)
#                 frames_since_last_seen += 1
#
#                 if frames_since_last_seen >= buffer_size:
#                     # 3. PERSON LEFT - STOP DISK WRITER
#                     is_recording = False
#                     # Signal the disk writer thread to finish and close the file
#                     video_write_queue.put(None)
#                     video_thread.join()  # Wait a split second to ensure it safely closed the file
#                     safe_name = current_match_name.replace(" ", "_")
#                     final_filename = f"{safe_name}_{event_timestamp}.mp4"
#
#                     # Decide paths based on person type
#                     if current_match_type == "FAMILY":
#                         final_path = os.path.join(FAMILY_DIR, final_filename)  # Full path for Windows to move the file
#                         db_video_path = f"media/events/family/{final_filename}"  # Clean path for PostgreSQL
#                     else:
#                         final_path = os.path.join(UNWANTED_DIR, final_filename)
#                         db_video_path = f"media/events/unwanted/{final_filename}"
#
#                     # Move the file on the hard drive using the full absolute path
#                     shutil.move(temp_filename, final_path)
#                     print(f"🛑 [{camera_name}] Event ended. Saved locally to: {final_path}")
#                     # 4. WRITE TO DATABASE
#                     db_event_string = f"{current_match_type.lower()}_detected"
#                     event_id = log_event_start(
#                         user_id=user_id,
#                         camera_id=camera_id,
#                         person_id=current_match_id,
#                         event_type=db_event_string,
#                         video_path=db_video_path  # <-- FIX: Save ONLY the clean relative path to the DB!
#                     )
#                     log_event_end(event_id)

import os
import warnings
import time
import collections
import shutil
import queue
import math
from datetime import datetime
import cv2
import threading
import numpy as np

# SUPPRESS NOISE
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

import tensorflow as tf

try:
    tf.config.set_visible_devices([], 'GPU')
except Exception:
    pass

from ultralytics import YOLO

from db.crud_events import log_event_start, log_event_end, create_unknown_person, log_object_interaction
from config import MODEL_PATH, PRE_ROLL_SECONDS, EVENTS_DIR, COOLDOWN_SECONDS
from ai_engine.face_recognition import identify_face, FaceCache
from db.session import SessionLocal
from sqlalchemy import text

# Define our new directory structure
TEMP_DIR = "media/temp"
FAMILY_DIR = os.path.join(EVENTS_DIR, "family")
UNWANTED_DIR = os.path.join(EVENTS_DIR, "unwanted")

os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(FAMILY_DIR, exist_ok=True)
os.makedirs(UNWANTED_DIR, exist_ok=True)


# ==========================================
# SCENE INTELLIGENCE HELPER FUNCTIONS
# ==========================================
def calculate_ioa(person_box, object_box):
    """
    Calculates Intersection over Object Area (IoA).
    Returns the percentage (0.0 to 1.0) of the object that is covered by the person.
    """
    px1, py1, px2, py2 = person_box
    ox1, oy1, ox2, oy2 = object_box

    # Determine the coordinates of the intersection rectangle
    x_left = max(px1, ox1)
    y_top = max(py1, oy1)
    x_right = min(px2, ox2)
    y_bottom = min(py2, oy2)

    if x_right < x_left or y_bottom < y_top:
        return 0.0  # No overlap at all

    # Calculate intersection area
    intersection_area = (x_right - x_left) * (y_bottom - y_top)

    # Calculate the object's total area
    object_area = (ox2 - ox1) * (oy2 - oy1)

    if object_area == 0:
        return 0.0

    return intersection_area / object_area


def get_center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def calculate_distance(p1, p2):
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def disk_writer_thread(filename, fps, width, height, frame_queue):
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(filename, fourcc, fps, (width, height))
    while True:
        frame = frame_queue.get()
        if frame is None:
            break
        writer.write(frame)
    writer.release()


def camera_worker_process(camera_id: str, camera_name: str, video_url: str, user_id: str, user_cache: dict,
                          alert_queue, command_queue):
    print(f"📹 [{camera_name}] Process started. Verifying connection...")

    cap = cv2.VideoCapture(video_url)

    if not cap.isOpened():
        print(f"❌ [{camera_name}] DEAD LINK! Cannot connect to {video_url}. Shutting down worker.")
        return

    success, _ = cap.read()
    if not success:
        print(f"❌ [{camera_name}] FAKE STREAM! Connected but receiving no video data. Shutting down worker.")
        cap.release()
        return

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps != fps: fps = 20.0

    buffer_size = int(fps * PRE_ROLL_SECONDS)
    frame_buffer = collections.deque(maxlen=buffer_size)

    camera_read_queue = queue.Queue(maxsize=int(fps * 2))
    stop_reader = False

    def camera_reader_task():
        while not stop_reader:
            ret, f = cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            if camera_read_queue.full():
                try:
                    camera_read_queue.get_nowait()
                except queue.Empty:
                    pass
            camera_read_queue.put(f)

    reader_thread = threading.Thread(target=camera_reader_task, daemon=True)
    reader_thread.start()

    try:
        model = YOLO(MODEL_PATH)
        model.to('cuda:0')
    except Exception as e:
        print(f"❌ [CAM] YOLO Error: {e}")
        return

    # --- VIDEO RECORDING STATE ---
    is_recording = False
    temp_filename = ""
    event_timestamp = ""
    frames_since_last_seen = 0
    person_visible_frames_count = 0  # NEW: Tracks how long the person was actually on screen

    video_write_queue = None
    video_thread = None

    is_identifying = False
    alert_sent_this_event = False
    identity_locked = False

    current_match_name = "Unknown"
    current_match_id = None
    current_match_type = "UNWANTED"

    TARGET_OBJECTS = {
        "backpack", "controller", "handbag", "headphones",
        "keys", "laptop", "smartphone", "tablet", "wallet", "watch"
    }
    scene_memory = {}
    pending_object_events = []

    # --- UPDATED THRESHOLDS ---
    MOVEMENT_THRESHOLD = 35  # Increased to ignore YOLO box jitter
    OVERLAP_REQUIRED = 0.30  # Person must cover at least 30% of the object's area
    FRAMES_TO_CONFIRM_MOTION = 3  # Debounce: Object must move for 3 consecutive frames

    def face_identification_task(crop_img):
        nonlocal is_identifying, alert_sent_this_event, identity_locked
        nonlocal current_match_name, current_match_id, current_match_type

        try:
            name, det_id, det_type = identify_face(crop_img, user_cache)
            current_time = datetime.now().isoformat()

            if name != "Unknown":
                print(f"✅ [{camera_name}] AI Identified: {name} ({det_type})")
                current_match_name = name
                current_match_id = det_id
                current_match_type = det_type

                if det_type == "UNWANTED" and not alert_sent_this_event:
                    alert_queue.put({
                        "type": "alert",
                        "user_id": user_id, "person_id": current_match_id,
                        "camera_id": camera_id, "camera_name": camera_name,
                        "person_name": current_match_name, "timestamp": current_time
                    })
                    alert_sent_this_event = True
            else:
                print(f"🚨 [{camera_name}] Unknown face! Generating new profile...")
                new_pid, generated_name = create_unknown_person(user_id, crop_img)

                if new_pid:
                    current_match_name = generated_name
                    current_match_id = new_pid
                    current_match_type = "UNWANTED"

                    try:
                        from deepface import DeepFace
                        rep = DeepFace.represent(img_path=crop_img, model_name="ArcFace", enforce_detection=False)[0]
                        user_cache[new_pid] = {"name": generated_name, "type": "UNWANTED",
                                               "embedding": rep["embedding"]}
                    except Exception as e:
                        print(f"⚠️ Could not cache new intruder: {e}")

                    if not alert_sent_this_event:
                        alert_queue.put({
                            "type": "alert",
                            "user_id": user_id, "person_id": current_match_id,
                            "camera_id": camera_id, "camera_name": camera_name,
                            "person_name": current_match_name, "timestamp": current_time
                        })
                        alert_sent_this_event = True

            identity_locked = True
        except Exception:
            pass
        finally:
            is_identifying = False

    while True:
        try:
            cmd = command_queue.get_nowait()
            if cmd.get("action") == "RELOAD_FACES" and cmd.get("user_id") == user_id:
                print(f"🔄 [{camera_name}] RELOAD COMMAND RECEIVED! Fetching fresh faces from DB...")
                new_cache = FaceCache.get_updated_user_cache(user_id)
                user_cache.clear()
                user_cache.update(new_cache)
                print(f"✅ [{camera_name}] Memory synced instantly.")
        except queue.Empty:
            pass

        try:
            frame = camera_read_queue.get(timeout=1.0)
        except queue.Empty:
            continue

        frame_buffer.append(frame)
        results = model.track(frame, persist=True, tracker="bytetrack.yaml", verbose=False, device='cuda:0')

        person_in_frame = False
        face_box = None
        current_persons = []
        current_objects = []

        for r in results:
            if r.boxes is not None and len(r.boxes) > 0:
                boxes = r.boxes.xyxy.int().cpu().numpy()
                classes = r.boxes.cls.int().cpu().numpy()
                track_ids = r.boxes.id.int().cpu().numpy() if r.boxes.id is not None else [None] * len(boxes)

                for box, cls, track_id in zip(boxes, classes, track_ids):
                    class_name = model.names[cls]

                    if class_name == "phone": class_name = "smartphone"

                    if class_name == "person" and track_id is not None:
                        person_in_frame = True
                        current_persons.append(box)
                    elif class_name == "human-face" and face_box is None:
                        face_box = box
                    elif class_name in TARGET_OBJECTS and track_id is not None:
                        current_objects.append({
                            "id": track_id, "class": class_name, "box": box, "center": get_center(box)
                        })

        # --- 1. EVENT LOGIC ---
        if person_in_frame:
            person_visible_frames_count += 1
            frames_since_last_seen = 0

            if not is_recording:
                is_recording = True
                identity_locked = False
                alert_sent_this_event = False
                current_match_name = "Unknown"
                current_match_id = None
                current_match_type = "UNWANTED"
                person_visible_frames_count = 1
                pending_object_events.clear()

                event_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                temp_filename = os.path.join(TEMP_DIR, f"temp_{camera_id}_{event_timestamp}.mp4")

                h, w, _ = frame.shape
                video_write_queue = queue.Queue()
                video_thread = threading.Thread(target=disk_writer_thread,
                                                args=(temp_filename, fps, w, h, video_write_queue))
                video_thread.start()

                for b_frame in frame_buffer:
                    video_write_queue.put(b_frame)

                print(f"🎥 [{camera_name}] Tracking locked. Checking for false positives...")
            else:
                video_write_queue.put(frame)

                if not identity_locked and not is_identifying and face_box is not None:
                    is_identifying = True
                    x1, y1, x2, y2 = map(int, face_box)
                    face_crop = frame[max(0, y1 - 10):y2 + 10, max(0, x1 - 10):x2 + 10].copy()
                    if face_crop.size > 0:
                        threading.Thread(target=face_identification_task, args=(face_crop,)).start()
                    else:
                        is_identifying = False

        # --- 2. OBJECT TRACKING LOGIC ---
        for obj in current_objects:
            obj_id = obj["id"]
            obj_center = obj["center"]

            if obj_id not in scene_memory:
                # Add motion_frames to memory initialization
                scene_memory[obj_id] = {
                    "class": obj["class"],
                    "center": obj_center,
                    "logged_this_event": False,
                    "motion_frames": 0
                }
                continue

            mem = scene_memory[obj_id]
            dist_moved = calculate_distance(mem["center"], obj_center)

            if dist_moved > MOVEMENT_THRESHOLD:
                mem["motion_frames"] += 1

                # Debounce: Only act if it's moving consistently
                if mem["motion_frames"] >= FRAMES_TO_CONFIRM_MOTION:
                    if is_recording and not mem["logged_this_event"]:
                        for p_box in current_persons:
                            # Use IoA instead of simple 1-pixel overlap check
                            overlap_ratio = calculate_ioa(p_box, obj["box"])

                            if overlap_ratio > OVERLAP_REQUIRED:
                                print(
                                    f"📦 [{camera_name}] Object Picked Up/Moved: {mem['class']} (Overlap: {overlap_ratio:.2f})")
                                pending_object_events.append(mem["class"])
                                mem["logged_this_event"] = True
                                break

                    # Update the baseline center only after confirming a real move
                    mem["center"] = obj_center
            else:
                # If the object stops moving, reset the motion debounce counter
                mem["motion_frames"] = 0

        # --- 3. EVENT END LOGIC ---
        if not person_in_frame:
            if is_recording:
                video_write_queue.put(frame)
                frames_since_last_seen += 1

                if frames_since_last_seen >= buffer_size:
                    is_recording = False
                    video_write_queue.put(None)
                    video_thread.join()

                    # Ghost Filter (Minimum Frame Threshold)
                    if person_visible_frames_count < (fps / 2):
                        print(f"👻 [{camera_name}] Ghost event discarded. (False Positive)")
                        if os.path.exists(temp_filename):
                            os.remove(temp_filename)
                        pending_object_events.clear()
                        for mem in scene_memory.values():
                            mem["logged_this_event"] = False
                        continue

                    safe_name = current_match_name.replace(" ", "_")
                    final_filename = f"{safe_name}_{event_timestamp}.mp4"

                    if current_match_type == "FAMILY":
                        final_path = os.path.join(FAMILY_DIR, final_filename)
                        db_video_path = f"media/events/family/{final_filename}"
                    else:
                        final_path = os.path.join(UNWANTED_DIR, final_filename)
                        db_video_path = f"media/events/unwanted/{final_filename}"

                    shutil.move(temp_filename, final_path)
                    print(f"🛑 [{camera_name}] Event ended. Saved locally to: {final_path}")

                    db_event_string = f"{current_match_type.lower()}_detected"

                    event_id = log_event_start(
                        user_id=user_id, camera_id=camera_id, person_id=current_match_id,
                        event_type=db_event_string, video_path=db_video_path
                    )

                    if event_id:
                        for obj_name in pending_object_events:
                            log_object_interaction(event_log_id=event_id, object_name=obj_name)

                    log_event_end(event_id)
                    pending_object_events.clear()

                    for mem in scene_memory.values():
                        mem["logged_this_event"] = False