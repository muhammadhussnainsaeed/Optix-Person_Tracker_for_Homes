# import os
# import warnings
# import time
# import collections
# import shutil
# import queue
# import math
# from datetime import datetime
# import cv2
# import threading
#
# from sqlalchemy import text
#
# from db.session import SessionLocal
#
# # ==========================================
# # ENVIRONMENT & SUPPRESSION SETUP
# # ==========================================
# # Suppress standard Python deprecation warnings
# warnings.filterwarnings("ignore", category=DeprecationWarning)
# warnings.filterwarnings("ignore", category=FutureWarning)
#
# # Suppress TensorFlow C++ backend logs to keep the console clean
# os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
# os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
#
# import tensorflow as tf
#
# # Force TensorFlow to ignore the GPU so YOLO can use it exclusively without memory conflicts
# try:
#     tf.config.set_visible_devices([], 'GPU')
# except Exception:
#     pass
#
# from ultralytics import YOLO
#
# from db.crud_events import log_event_start, log_event_end, create_unknown_person, log_object_interaction
# from config import MODEL_PATH, PRE_ROLL_SECONDS, EVENTS_DIR, COOLDOWN_SECONDS
# from ai_engine.face_recognition import identify_face, FaceCache
#
# # ==========================================
# # DIRECTORY STRUCTURE SETUP
# # ==========================================
# # Define where temporary and finalized video events will be saved
# TEMP_DIR = "media/temp"
# FAMILY_DIR = os.path.join(EVENTS_DIR, "family")
# UNWANTED_DIR = os.path.join(EVENTS_DIR, "unwanted")
#
# # Ensure these directories exist on disk before the script runs
# os.makedirs(TEMP_DIR, exist_ok=True)
# os.makedirs(FAMILY_DIR, exist_ok=True)
# os.makedirs(UNWANTED_DIR, exist_ok=True)
#
#
# # ==========================================
# # SCENE INTELLIGENCE HELPER FUNCTIONS
# # ==========================================
# def calculate_ioa(person_box, object_box):
#     """
#     Calculates Intersection over Object Area (IoA).
#     Unlike standard IoU (Intersection over Union), IoA checks how much of the
#     TARGET OBJECT is covered by the person. This is better for detecting if a
#     person's hand/body is actively overlapping a small object like a phone or keys.
#     Returns a float from 0.0 to 1.0 (0% to 100%).
#     """
#     px1, py1, px2, py2 = person_box
#     ox1, oy1, ox2, oy2 = object_box
#
#     # Determine the coordinates of the overlapping rectangle
#     x_left = max(px1, ox1)
#     y_top = max(py1, oy1)
#     x_right = min(px2, ox2)
#     y_bottom = min(py2, oy2)
#
#     # If the boundaries don't overlap, return 0
#     if x_right < x_left or y_bottom < y_top:
#         return 0.0
#
#     # Calculate the area of the overlapping section
#     intersection_area = (x_right - x_left) * (y_bottom - y_top)
#
#     # Calculate the total area of the object itself
#     object_area = (ox2 - ox1) * (oy2 - oy1)
#
#     if object_area == 0:
#         return 0.0
#
#     return intersection_area / object_area
#
#
# def get_center(box):
#     """Calculates the center (x, y) point of a bounding box."""
#     return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
#
#
# def calculate_distance(p1, p2):
#     """Calculates the Euclidean distance between two (x, y) points in pixels."""
#     return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)
#
#
# def disk_writer_thread(filename, fps, width, height, frame_queue):
#     """
#     A background worker that pulls frames from a queue and writes them to an MP4 file.
#     This prevents the main YOLO process from freezing while waiting for slow hard drives.
#     """
#     fourcc = cv2.VideoWriter_fourcc(*'mp4v')
#     writer = cv2.VideoWriter(filename, fourcc, fps, (width, height))
#     while True:
#         frame = frame_queue.get()
#         if frame is None:  # None is the poison pill to kill the thread
#             break
#         writer.write(frame)
#     writer.release()
#
#
# from datetime import datetime
#
# def check_family_rule(db, user_id, person_id, person_name, camera_id, camera_name):
#     """
#     Evaluates monitoring rules using the new Junction Table structure.
#     Returns an alert payload if a rule is triggered, else None.
#     """
#     now_time = datetime.now().time()
#     current_timestamp = datetime.now().isoformat()
#
#     # Optimized Query: JOINs rules with the junction table to check camera access
#     query = text("""
#                  SELECT r.id, r.rule_name, r.from_time, r.to_time
#                  FROM monitoring_rules r
#                           JOIN monitoring_rule_cameras mrc ON r.id = mrc.rule_id
#                  WHERE r.user_id = :user_id
#                    AND r.person_id = :person_id
#                    AND r.is_active = true
#                    AND mrc.camera_id = :camera_id
#                  """)
#
#     result = db.execute(query, {
#         "user_id": str(user_id),
#         "person_id": str(person_id),
#         "camera_id": str(camera_id)
#     })
#
#     rules = result.mappings().all()
#
#     for rule in rules:
#         from_t = rule["from_time"]
#         to_t = rule["to_time"]
#         is_triggered = False
#
#         # 1. Check if it's an "All Day" rule (Both are NULL)
#         if from_t is None and to_t is None:
#             is_triggered = True
#         else:
#             # Handle string to time conversion if necessary
#             if isinstance(from_t, str):
#                 from_t = datetime.strptime(from_t, "%H:%M:%S").time()
#             if isinstance(to_t, str):
#                 to_t = datetime.strptime(to_t, "%H:%M:%S").time()
#
#             # 2. Match time window (Handling midnight wrap-around)
#             if from_t <= to_t:
#                 is_triggered = from_t <= now_time <= to_t
#             else:
#                 is_triggered = now_time >= from_t or now_time <= to_t
#
#         if is_triggered:
#             # We use the actual rule_name from the database now!
#             rule_label = rule["rule_name"]
#             print(f"🔔 [RULE MATCH] {person_name} triggered '{rule_label}' on {camera_name}")
#
#             return {
#                 "type": "smart_alert",
#                 "user_id": str(user_id),
#                 "person_id": str(person_id),
#                 "camera_id": str(camera_id),
#                 "camera_name": camera_name,
#                 "person_name": person_name,
#                 "rule_name": rule_label,
#                 "timestamp": current_timestamp
#             }
#
#     return None
#
# # ==========================================
# # MAIN CAMERA WORKER PROCESS
# # ==========================================
# def camera_worker_process(camera_id: str, camera_name: str, video_url: str, user_id: str, is_private: bool, user_cache: dict,
#                           alert_queue, command_queue):
#     print(f"📹 [{camera_name}] Process started. Verifying connection...")
#
#     cap = cv2.VideoCapture(video_url)
#
#     # Validate camera connection
#     if not cap.isOpened():
#         print(f"❌ [{camera_name}] DEAD LINK! Cannot connect to {video_url}. Shutting down worker.")
#         return
#
#     # Validate stream actually has video data
#     success, _ = cap.read()
#     if not success:
#         print(f"❌ [{camera_name}] FAKE STREAM! Connected but receiving no video data. Shutting down worker.")
#         cap.release()
#         return
#
#     # Set OpenCV buffer low to reduce stream latency
#     cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)
#
#     # Calculate FPS, defaulting to 20.0 if the camera doesn't provide it
#     fps = cap.get(cv2.CAP_PROP_FPS)
#     if not fps or fps != fps: fps = 20.0
#
#     # Initialize a rolling buffer to store the last few seconds of video (Pre-Roll)
#     # This allows us to save video from BEFORE the person triggered the event.
#     buffer_size = int(fps * PRE_ROLL_SECONDS)
#     frame_buffer = collections.deque(maxlen=buffer_size)
#
#     # Setup the async frame reader thread
#     camera_read_queue = queue.Queue(maxsize=int(fps * 2))
#     stop_reader = False
#
#     def camera_reader_task():
#         """Reads frames as fast as possible in the background so YOLO doesn't drop frames."""
#         while not stop_reader:
#             ret, f = cap.read()
#             if not ret:
#                 time.sleep(0.01)
#                 continue
#             if camera_read_queue.full():
#                 try:
#                     camera_read_queue.get_nowait()  # Drop oldest frame if queue is full
#                 except queue.Empty:
#                     pass
#             camera_read_queue.put(f)
#
#     reader_thread = threading.Thread(target=camera_reader_task, daemon=True)
#     reader_thread.start()
#
#     # Load the YOLO model onto the GPU
#     try:
#         model = YOLO(MODEL_PATH)
#         model.to('cuda:0')
#     except Exception as e:
#         print(f"❌ [CAM] YOLO Error: {e}")
#         return
#
#     # --- STATE VARIABLES: VIDEO RECORDING ---
#     event_start_time = None
#     is_recording = False
#     temp_filename = ""
#     event_timestamp = ""
#     frames_since_last_seen = 0
#     person_visible_frames_count = 0  # Tracks actual presence to filter out "ghosts" (flashes/glitches)
#
#     video_write_queue = None
#     video_thread = None
#
#     # --- STATE VARIABLES: IDENTITY TRACKING ---
#     is_identifying = False
#     alert_sent_this_event = False
#     identity_locked = False
#     current_match_name = "Unknown"
#     current_match_id = None
#     current_match_type = "UNWANTED"
#
#     # --- STATE VARIABLES: SCENE OBJECTS ---
#     TARGET_OBJECTS = {
#         "backpack", "controller", "handbag", "headphones",
#         "keys", "laptop", "smartphone", "tablet", "wallet", "watch", "glasses"
#     }
#     scene_memory = {}  # Stores the location and status of static objects
#     pending_object_events = []  # Objects picked up during the current event
#
#     # --- BEHAVIOR THRESHOLDS ---
#     MOVEMENT_THRESHOLD = 35  # Pixels an object must move to ignore bounding box jitter
#     OVERLAP_REQUIRED = 0.05  # Person must cover at least 4% of the object to pick it up
#     FRAMES_TO_CONFIRM_MOTION = 3  # Debounce: Object must move for 3 consecutive frames
#     FRAMES_TO_ARM = int(fps * 10)  # Time an object must sit completely still to become "Armed"
#     FRAMES_TO_FORGET = int(fps * 5)  # Grace period before forgetting an object hidden by a person
#
#     def face_identification_task(crop_img):
#         """Background task to send a cropped face to the AI Engine for identification."""
#         nonlocal is_identifying, alert_sent_this_event, identity_locked
#         nonlocal current_match_name, current_match_id, current_match_type
#
#         try:
#             name, det_id, det_type = identify_face(crop_img, user_cache)
#             current_time = datetime.now().isoformat()
#
#             if name != "Unknown":
#                 # Known person found
#                 print(f"✅ [{camera_name}] AI Identified: {name} ({det_type})")
#                 current_match_name = name
#                 current_match_id = det_id
#                 current_match_type = det_type
#
#                 # Trigger alert if the known person is flagged as UNWANTED
#                 if det_type == "UNWANTED" and not alert_sent_this_event:
#                     alert_queue.put({
#                         "type": "alert",
#                         "user_id": user_id, "person_id": current_match_id,
#                         "camera_id": camera_id, "camera_name": camera_name,
#                         "person_name": current_match_name, "timestamp": current_time
#                     })
#                     alert_sent_this_event = True
#
#                 elif det_type == "FAMILY" and not alert_sent_this_event:
#                     with SessionLocal() as db:
#                         alert_payload = check_family_rule(
#                             db, user_id, current_match_id, current_match_name, camera_id, camera_name
#                         )
#
#                     if alert_payload:
#                         alert_queue.put(alert_payload)
#                         alert_sent_this_event = True
#             else:
#                 # Intruder found: Generate a new profile on the fly
#                 print(f"🚨 [{camera_name}] Unknown face! Generating new profile...")
#                 new_pid, generated_name = create_unknown_person(user_id, crop_img)
#
#                 if new_pid:
#                     current_match_name = generated_name
#                     current_match_id = new_pid
#                     current_match_type = "UNWANTED"
#
#                     # Add new intruder to the local RAM cache so we don't alert on them twice
#                     try:
#                         from deepface import DeepFace
#                         rep = DeepFace.represent(img_path=crop_img, model_name="ArcFace", enforce_detection=False)[0]
#                         user_cache[new_pid] = {"name": generated_name, "type": "UNWANTED",
#                                                "embedding": rep["embedding"]}
#                     except Exception as e:
#                         print(f"⚠️ Could not cache new intruder: {e}")
#
#                     # Trigger alert for the new intruder
#                     if not alert_sent_this_event:
#                         alert_queue.put({
#                             "type": "alert",
#                             "user_id": user_id, "person_id": current_match_id,
#                             "camera_id": camera_id, "camera_name": camera_name,
#                             "person_name": current_match_name, "timestamp": current_time
#                         })
#                         alert_sent_this_event = True
#
#             identity_locked = True
#         except Exception:
#             pass
#         finally:
#             # Release the lock so the system can scan faces again if needed
#             is_identifying = False
#
#     # ==========================================
#     # MAIN CAMERA LOOP
#     # ==========================================
#     while True:
#         # 1. Process incoming commands (e.g., UI requested a memory sync)
#         try:
#             cmd = command_queue.get_nowait()
#             if cmd.get("action") == "RELOAD_FACES" and cmd.get("user_id") == user_id:
#                 print(f"🔄 [{camera_name}] RELOAD COMMAND RECEIVED! Fetching fresh faces from DB...")
#                 new_cache = FaceCache.get_updated_user_cache(user_id)
#                 user_cache.clear()
#                 user_cache.update(new_cache)
#                 print(f"✅ [{camera_name}] Memory synced instantly.")
#         except queue.Empty:
#             pass
#
#         # 2. Get the latest frame from the reader thread
#         try:
#             frame = camera_read_queue.get(timeout=1.0)
#         except queue.Empty:
#             continue
#
#         frame_buffer.append(frame)  # Keep the rolling pre-roll buffer updated
#
#         # 3. Run YOLO inference using ByteTrack for continuous object ID assignment
#         results = model.track(frame, persist=True, tracker="bytetrack.yaml", verbose=False, device='cuda:0')
#
#         # Variables to store findings for this specific frame
#         person_in_frame = False
#         face_box = None
#         current_persons = []
#         current_objects = []
#
#         # 4. Parse the YOLO results
#         for r in results:
#             if r.boxes is not None and len(r.boxes) > 0:
#                 boxes = r.boxes.xyxy.int().cpu().numpy()
#                 classes = r.boxes.cls.int().cpu().numpy()
#                 track_ids = r.boxes.id.int().cpu().numpy() if r.boxes.id is not None else [None] * len(boxes)
#
#                 for box, cls, track_id in zip(boxes, classes, track_ids):
#                     class_name = model.names[cls]
#
#                     if class_name == "person" and track_id is not None:
#                         person_in_frame = True
#                         current_persons.append(box)
#                     elif class_name == "human-face" and face_box is None:
#                         face_box = box  # Grab the first face we see for identification
#                     elif class_name in TARGET_OBJECTS and track_id is not None:
#                         current_objects.append({
#                             "id": track_id, "class": class_name, "box": box, "center": get_center(box)
#                         })
#
#         # ==========================================
#         # --- 1. EVENT LOGIC (RECORDING & ID) ---
#         # ==========================================
#         if person_in_frame:
#             person_visible_frames_count += 1
#             frames_since_last_seen = 0  # Reset the "lost track" counter
#
#             if not is_recording:
#                 # A person just walked in! Start a new recording event.
#                 is_recording = True
#                 identity_locked = False
#                 alert_sent_this_event = False
#                 current_match_name = "Unknown"
#                 current_match_id = None
#                 current_match_type = "UNWANTED"
#                 person_visible_frames_count = 1
#                 pending_object_events.clear()
#
#                 event_start_time = datetime.now().astimezone()
#                 event_timestamp = event_start_time.strftime("%Y%m%d_%H%M%S")
#                 temp_filename = os.path.join(TEMP_DIR, f"temp_{camera_id}_{event_timestamp}.mp4")
#
#                 h, w, _ = frame.shape
#                 video_write_queue = queue.Queue()
#
#                 # Start the background writer thread
#                 video_thread = threading.Thread(target=disk_writer_thread,
#                                                 args=(temp_filename, fps, w, h, video_write_queue))
#                 video_thread.start()
#
#                 # Dump the entire Pre-Roll buffer into the new video so we see them walking in
#                 for b_frame in frame_buffer:
#                     video_write_queue.put(b_frame)
#
#                 print(f"🎥 [{camera_name}] Tracking locked. Checking for false positives...")
#             else:
#                 # We are actively recording, append the current frame
#                 video_write_queue.put(frame)
#
#                 # Trigger face identification if we haven't locked an identity yet
#                 if not identity_locked and not is_identifying and face_box is not None:
#                     is_identifying = True
#                     x1, y1, x2, y2 = map(int, face_box)
#                     # Add a 10px padding around the face for better AI accuracy
#                     face_crop = frame[max(0, y1 - 10):y2 + 10, max(0, x1 - 10):x2 + 10].copy()
#                     if face_crop.size > 0:
#                         threading.Thread(target=face_identification_task, args=(face_crop,)).start()
#                     else:
#                         is_identifying = False
#
#         # ==========================================
#         # --- 2. SCENE OBJECT TRACKING LOGIC ---
#         # ==========================================
#         # This checks all targeted objects to see if they are being interacted with.
#         for obj in current_objects:
#             obj_id = obj["id"]
#             obj_center = obj["center"]
#
#             # Initialize a new object in memory if we haven't seen it before
#             if obj_id not in scene_memory:
#                 scene_memory[obj_id] = {
#                     "class": obj["class"],
#                     "center": obj_center,
#                     "box": obj["box"],
#                     "logged_this_event": False,
#                     "motion_frames": 0,
#                     "static_frames": 0,  # Counts how long it rests
#                     "is_armed": False,  # Turns True after 10s of resting
#                     "occluded_frames": 0  # Counts how long it is hidden from view
#                 }
#                 continue
#
#             mem = scene_memory[obj_id]
#             mem["box"] = obj["box"]
#             dist_moved = calculate_distance(mem["center"], obj_center)
#
#             # Check if the object is STATIONARY (Resting)
#             if dist_moved <= MOVEMENT_THRESHOLD:
#                 mem["motion_frames"] = 0
#                 mem["static_frames"] += 1
#
#                 # If it has been sitting still for 10 seconds, ARM IT.
#                 if mem["static_frames"] >= FRAMES_TO_ARM and not mem["is_armed"]:
#                     mem["is_armed"] = True
#                     print(f"🛡️ [{camera_name}] {mem['class']} has rested for 10s. Now armed and watching.")
#                     # Recalibrate its baseline center to its current resting place
#                     mem["center"] = obj_center
#
#             # Check if the object is MOVING
#             else:
#                 mem["static_frames"] = 0  # It moved! Reset the 10-second resting timer.
#
#                 # Only evaluate for alerts if the object was previously "Armed"
#                 if mem["is_armed"]:
#                     mem["motion_frames"] += 1
#
#                     # Debounce Check: Must move for 3 consecutive frames to filter out camera glitches
#                     if mem["motion_frames"] >= FRAMES_TO_CONFIRM_MOTION:
#                         if is_recording and not mem["logged_this_event"]:
#                             # Confirm a person's hand/body is overlapping the object
#                             for p_box in current_persons:
#                                 overlap_ratio = calculate_ioa(p_box, obj["box"])
#                                 if overlap_ratio > OVERLAP_REQUIRED:
#                                     print(
#                                         f"📦 [{camera_name}] Armed Object Moved: {mem['class']} (Overlap: {overlap_ratio:.2f})")
#                                     pending_object_events.append(mem["class"])
#                                     mem["logged_this_event"] = True
#
#                                     # Disarm it so it doesn't spam alerts while being carried around
#                                     mem["is_armed"] = False
#                                     break
#
#                         # Update the baseline center as the object moves away
#                         mem["center"] = obj_center
#                 else:
#                     # It is moving, but it wasn't armed yet (e.g., someone just walked into the room carrying it).
#                     # We simply update its center to track where it is going.
#                     mem["center"] = obj_center
#
#         # ==========================================
#         # NEW: GRACE-PERIOD MEMORY CLEANUP
#         # ==========================================
#         # This prevents RAM crashes by deleting objects from memory if they are permanently gone.
#         current_object_ids = []
#         for obj in current_objects:
#             current_object_ids.append(obj["id"])
#
#         stale_ids = []
#
#         for memory_id, mem in scene_memory.items():
#             if memory_id not in current_object_ids:
#
#                 # THE DISAPPEARANCE CHECK: Did it JUST vanish this exact frame?
#                 if mem["occluded_frames"] == 0 and mem["is_armed"]:
#                     if is_recording and not mem["logged_this_event"]:
#                         for p_box in current_persons:
#                             # Check if the person is touching the object's LAST KNOWN location
#                             overlap_ratio = calculate_ioa(p_box, mem["box"])
#
#                             # Using a forgiving 5% overlap threshold for hands/arms
#                             if overlap_ratio > 0.05:
#                                 print(f"🪄📦 [{camera_name}] Armed Object Grabbed/Vanished: {mem['class']}")
#                                 pending_object_events.append(mem["class"])
#                                 mem["logged_this_event"] = True
#                                 mem["is_armed"] = False
#                                 break
#
#                 # Start counting how long it has been hidden
#                 mem["occluded_frames"] += 1
#
#                 # If it has been hidden for over 5 seconds, mark it for deletion
#                 if mem["occluded_frames"] >= FRAMES_TO_FORGET:
#                     stale_ids.append(memory_id)
#             else:
#                 # The object is visible! Reset the occluded counter back to 0
#                 mem["occluded_frames"] = 0
#
#         # Delete only the objects that exceeded the 5-second grace period
#         for stale_id in stale_ids:
#             del scene_memory[stale_id]
#
#         # ==========================================
#         # --- 3. EVENT END LOGIC ---
#         # ==========================================
#         if not person_in_frame:
#             if is_recording:
#                 # Continue recording the "post-roll" (the time after they leave the frame)
#                 video_write_queue.put(frame)
#                 frames_since_last_seen += 1
#
#                 # If they have been gone longer than the buffer size, end the event
#                 if frames_since_last_seen >= buffer_size:
#                     is_recording = False
#                     video_write_queue.put(None)  # Tell the writer thread to close the file
#
#                     # Ghost Filter: Did a brief shadow trigger the camera?
#                     if person_visible_frames_count < (fps / 2):
#                         print(f"👻 [{camera_name}] Ghost event discarded. (False Positive)")
#                         video_thread.join()  # Wait for file to close safely
#                         if os.path.exists(temp_filename):
#                             os.remove(temp_filename)  # Delete the useless video
#                         pending_object_events.clear()
#                         for mem in scene_memory.values():
#                             mem["logged_this_event"] = False
#                         continue
#
#                     # Fallback Alert: They left, but we never saw their face!
#                     if not alert_sent_this_event and current_match_id is None:
#                         print(f"⚠️ [{camera_name}] Person left frame without showing face. Sending alert!")
#                         alert_queue.put({
#                             "type": "alert",
#                             "user_id": user_id,
#                             "person_id": None,
#                             "camera_id": camera_id,
#                             "camera_name": camera_name,
#                             "person_name": "Identity Unconfirmed",
#                             "timestamp": datetime.now().isoformat()
#                         })
#                         alert_sent_this_event = True
#
#                     # Generate final filename based on who we identified
#                     safe_name = current_match_name.replace(" ", "_")
#                     final_filename = f"{safe_name}_{event_timestamp}.mp4"
#
#                     # Determine final storage directory based on threat level
#                     if current_match_type == "FAMILY":
#                         final_path = os.path.join(FAMILY_DIR, final_filename)
#                         db_video_path = f"media/events/family/{final_filename}"
#                     else:
#                         final_path = os.path.join(UNWANTED_DIR, final_filename)
#                         db_video_path = f"media/events/unwanted/{final_filename}"
#
#                     # Wait for the background thread to finish saving and unlock the file
#                     video_thread.join()
#
#                     # Move file from Temp to Final location
#                     shutil.move(temp_filename, final_path)
#                     print(f"🛑 [{camera_name}] Event ended. Saved locally to: {final_path}")
#
#                     # Determine string identifier for PostgreSQL
#                     db_event_string = f"{current_match_type.lower()}_detected"
#
#                     if is_private:
#                         db_video_path = ""
#
#                     # Commit primary event to the database
#                     event_id = log_event_start(
#                         user_id=user_id, camera_id=camera_id, person_id=current_match_id,
#                         event_type=db_event_string, video_path=db_video_path, detected_at= str(event_start_time)
#                     )
#
#                     # Commit any objects picked up during this event to the database
#                     if event_id:
#                         for obj_name in pending_object_events:
#                             log_object_interaction(event_log_id=event_id, object_name=obj_name)
#
#                     # Mark event as complete in the database
#                     log_event_end(event_id)
#
#                     # Reset memory states for the next event
#                     pending_object_events.clear()
#                     for mem in scene_memory.values():
#                         mem["logged_this_event"] = False


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

from sqlalchemy import text

from db.session import SessionLocal

# ==========================================
# ENVIRONMENT & SUPPRESSION SETUP
# ==========================================
# Suppress standard Python deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

# Suppress TensorFlow C++ backend logs to keep the console clean
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

import tensorflow as tf

# Force TensorFlow to ignore the GPU so YOLO can use it exclusively without memory conflicts
try:
    tf.config.set_visible_devices([], 'GPU')
except Exception:
    pass

from ultralytics import YOLO

from db.crud_events import log_event_start, log_event_end, create_unknown_person, log_object_interaction
from config import MODEL_PATH, PRE_ROLL_SECONDS, EVENTS_DIR, COOLDOWN_SECONDS
from ai_engine.face_recognition import identify_face, FaceCache

# ==========================================
# DIRECTORY STRUCTURE SETUP
# ==========================================
# Define where temporary and finalized video events will be saved
TEMP_DIR = "media/temp"
FAMILY_DIR = os.path.join(EVENTS_DIR, "family")
UNWANTED_DIR = os.path.join(EVENTS_DIR, "unwanted")

# Ensure these directories exist on disk before the script runs
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(FAMILY_DIR, exist_ok=True)
os.makedirs(UNWANTED_DIR, exist_ok=True)


# ==========================================
# SCENE INTELLIGENCE HELPER FUNCTIONS
# ==========================================
def calculate_ioa(person_box, object_box):
    """
    Calculates Intersection over Object Area (IoA).
    Unlike standard IoU (Intersection over Union), IoA checks how much of the
    TARGET OBJECT is covered by the person. This is better for detecting if a
    person's hand/body is actively overlapping a small object like a phone or keys.
    Returns a float from 0.0 to 1.0 (0% to 100%).
    """
    px1, py1, px2, py2 = person_box
    ox1, oy1, ox2, oy2 = object_box

    # Determine the coordinates of the overlapping rectangle
    x_left = max(px1, ox1)
    y_top = max(py1, oy1)
    x_right = min(px2, ox2)
    y_bottom = min(py2, oy2)

    # If the boundaries don't overlap, return 0
    if x_right < x_left or y_bottom < y_top:
        return 0.0

    # Calculate the area of the overlapping section
    intersection_area = (x_right - x_left) * (y_bottom - y_top)

    # Calculate the total area of the object itself
    object_area = (ox2 - ox1) * (oy2 - oy1)

    if object_area == 0:
        return 0.0

    return intersection_area / object_area


def get_center(box):
    """Calculates the center (x, y) point of a bounding box."""
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def calculate_distance(p1, p2):
    """Calculates the Euclidean distance between two (x, y) points in pixels."""
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def disk_writer_thread(filename, fps, width, height, frame_queue):
    """
    A background worker that pulls frames from a queue and writes them to an MP4 file.
    This prevents the main YOLO process from freezing while waiting for slow hard drives.
    """
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(filename, fourcc, fps, (width, height))
    while True:
        frame = frame_queue.get()
        if frame is None:  # None is the poison pill to kill the thread
            break
        writer.write(frame)
    writer.release()


def check_family_rule(db, user_id, person_id, person_name, camera_id, camera_name):
    """
    Evaluates monitoring rules using the Junction Table structure.
    Returns an alert payload if a rule is triggered, else None.
    """
    now_time = datetime.now().time()
    current_timestamp = datetime.now().isoformat()

    # Optimized Query: JOINs rules with the junction table to check camera access
    query = text("""
                 SELECT r.id, r.rule_name, r.from_time, r.to_time
                 FROM monitoring_rules r
                          JOIN monitoring_rule_cameras mrc ON r.id = mrc.rule_id
                 WHERE r.user_id = :user_id
                   AND r.person_id = :person_id
                   AND r.is_active = true
                   AND mrc.camera_id = :camera_id
                 """)

    result = db.execute(query, {
        "user_id": str(user_id),
        "person_id": str(person_id),
        "camera_id": str(camera_id)
    })

    rules = result.mappings().all()

    for rule in rules:
        from_t = rule["from_time"]
        to_t = rule["to_time"]
        is_triggered = False

        # 1. Check if it's an "All Day" rule (Both are NULL)
        if from_t is None and to_t is None:
            is_triggered = True
        else:
            # Handle string to time conversion if necessary
            if isinstance(from_t, str):
                from_t = datetime.strptime(from_t, "%H:%M:%S").time()
            if isinstance(to_t, str):
                to_t = datetime.strptime(to_t, "%H:%M:%S").time()

            # 2. Match time window (Handling midnight wrap-around)
            if from_t <= to_t:
                is_triggered = from_t <= now_time <= to_t
            else:
                is_triggered = now_time >= from_t or now_time <= to_t

        if is_triggered:
            rule_label = rule["rule_name"]
            print(f"🔔 [RULE MATCH] {person_name} triggered '{rule_label}' on {camera_name}")

            return {
                "type": "smart_alert",
                "user_id": str(user_id),
                "person_id": str(person_id),
                "camera_id": str(camera_id),
                "camera_name": camera_name,
                "person_name": person_name,
                "rule_name": rule_label,
                "timestamp": current_timestamp
            }

    return None


# ==========================================
# MAIN CAMERA WORKER PROCESS
# ==========================================
def camera_worker_process(camera_id: str, camera_name: str, video_url: str, user_id: str, is_private: bool,
                          user_cache: dict,
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
    if not fps or math.isnan(fps): fps = 20.0

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

    # --- STATE VARIABLES: SESSION ARCHITECTURE ---
    # Replaces monolithic is_recording state to handle multiple simultaneous people
    active_sessions = {}

    # --- STATE VARIABLES: SCENE OBJECTS ---
    TARGET_OBJECTS = {
        "backpack", "controller", "handbag", "headphones",
        "keys", "laptop", "smartphone", "tablet", "wallet", "watch", "glasses"
    }
    scene_memory = {}

    # --- BEHAVIOR THRESHOLDS ---
    MOVEMENT_THRESHOLD = 35
    OVERLAP_REQUIRED = 0.05
    FRAMES_TO_CONFIRM_MOTION = 3
    FRAMES_TO_ARM = int(fps * 10)
    FRAMES_TO_FORGET = int(fps * 5)

    def face_identification_task(crop_img, session_ref):
        """Background task isolated to a specific person's tracking session."""
        try:
            name, det_id, det_type = identify_face(crop_img, user_cache)
            current_time = datetime.now().isoformat()

            if name != "Unknown":
                print(f"✅ [{camera_name}] AI Identified Track {session_ref['track_id']}: {name} ({det_type})")
                session_ref["match_name"] = name
                session_ref["match_id"] = det_id
                session_ref["match_type"] = det_type

                if det_type == "UNWANTED" and not session_ref["alert_sent"]:
                    alert_queue.put({
                        "type": "alert", "user_id": user_id, "person_id": det_id,
                        "camera_id": camera_id, "camera_name": camera_name,
                        "person_name": name, "timestamp": current_time
                    })
                    session_ref["alert_sent"] = True

                elif det_type == "FAMILY" and not session_ref["alert_sent"]:
                    with SessionLocal() as db:
                        alert_payload = check_family_rule(db, user_id, det_id, name, camera_id, camera_name)
                    if alert_payload:
                        alert_queue.put(alert_payload)
                        session_ref["alert_sent"] = True
            else:
                print(f"🚨 [{camera_name}] Unknown face on Track {session_ref['track_id']}! Generating profile...")
                new_pid, generated_name = create_unknown_person(user_id, crop_img)

                if new_pid:
                    session_ref["match_name"] = generated_name
                    session_ref["match_id"] = new_pid
                    session_ref["match_type"] = "UNWANTED"

                    try:
                        from deepface import DeepFace
                        rep = DeepFace.represent(img_path=crop_img, model_name="ArcFace", enforce_detection=False)[0]
                        user_cache[new_pid] = {"name": generated_name, "type": "UNWANTED",
                                               "embedding": rep["embedding"]}
                    except Exception as e:
                        print(f"⚠️ Could not cache new intruder: {e}")

                    if not session_ref["alert_sent"]:
                        alert_queue.put({
                            "type": "alert", "user_id": user_id, "person_id": new_pid,
                            "camera_id": camera_id, "camera_name": camera_name,
                            "person_name": generated_name, "timestamp": current_time
                        })
                        session_ref["alert_sent"] = True

            session_ref["identity_locked"] = True
        except Exception:
            pass
        finally:
            session_ref["is_identifying"] = False

    # ==========================================
    # MAIN CAMERA LOOP
    # ==========================================
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

        current_persons = {}  # Map track_id -> bounding box
        current_faces = []  # List of face bounding boxes
        current_objects = []

        for r in results:
            if r.boxes is not None and len(r.boxes) > 0:
                boxes = r.boxes.xyxy.int().cpu().numpy()
                classes = r.boxes.cls.int().cpu().numpy()
                track_ids = r.boxes.id.int().cpu().numpy() if r.boxes.id is not None else [None] * len(boxes)

                for box, cls, track_id in zip(boxes, classes, track_ids):
                    class_name = model.names[cls]

                    if class_name == "person" and track_id is not None:
                        current_persons[track_id] = box
                    elif class_name == "human-face":
                        current_faces.append(box)
                    elif class_name in TARGET_OBJECTS and track_id is not None:
                        current_objects.append({
                            "id": track_id, "class": class_name, "box": box, "center": get_center(box)
                        })

        # ==========================================
        # --- 1. MULTI-PERSON EVENT LOGIC ---
        # ==========================================

        # A. Register new persons and update existing ones
        for p_id, p_box in current_persons.items():
            if p_id not in active_sessions:
                # NEW PERSON ENTERS: Spin up a dedicated tracker and video thread
                event_start_time = datetime.now().astimezone()
                event_timestamp = event_start_time.strftime("%Y%m%d_%H%M%S")
                temp_filename = os.path.join(TEMP_DIR, f"temp_{camera_id}_tr{p_id}_{event_timestamp}.mp4")

                h, w, _ = frame.shape
                v_queue = queue.Queue()
                v_thread = threading.Thread(target=disk_writer_thread, args=(temp_filename, fps, w, h, v_queue))
                v_thread.start()

                active_sessions[p_id] = {
                    "track_id": p_id,
                    "start_time": event_start_time,
                    "frames_since_last_seen": 0,
                    "visible_frames_count": 1,
                    "is_identifying": False,
                    "identity_locked": False,
                    "match_name": "Unknown",
                    "match_id": None,
                    "match_type": "UNWANTED",
                    "alert_sent": False,
                    "pending_objects": [],  # Objects picked up by THIS specific person
                    "video_queue": v_queue,
                    "video_thread": v_thread,
                    "temp_filename": temp_filename,
                    "event_timestamp": event_timestamp
                }

                # Dump pre-roll buffer into their specific video
                for b_frame in frame_buffer:
                    v_queue.put(b_frame)

                print(f"🎥 [{camera_name}] Track {p_id} started. Checking identity...")

            else:
                # EXISTING PERSON UPDATES
                session = active_sessions[p_id]
                session["frames_since_last_seen"] = 0
                session["visible_frames_count"] += 1

                # FACE ASSOCIATION: Check if any detected face geographically belongs to THIS person's body
                if not session["identity_locked"] and not session["is_identifying"]:
                    for f_box in current_faces:
                        fc = get_center(f_box)
                        # Check if the center of the face falls inside this person's bounding box boundaries
                        if p_box[0] < fc[0] < p_box[2] and p_box[1] < fc[1] < p_box[3]:
                            session["is_identifying"] = True
                            x1, y1, x2, y2 = map(int, f_box)
                            face_crop = frame[max(0, y1 - 10):y2 + 10, max(0, x1 - 10):x2 + 10].copy()

                            if face_crop.size > 0:
                                threading.Thread(target=face_identification_task, args=(face_crop, session)).start()
                            else:
                                session["is_identifying"] = False
                            break  # Face assigned to this person, move on

        # B. Write current frame to all active sessions (so everyone gets recorded continuously)
        for p_id, session in active_sessions.items():
            if p_id in current_persons or session["frames_since_last_seen"] < buffer_size:
                session["video_queue"].put(frame)

        # ==========================================
        # --- 2. MULTI-AGENT SCENE OBJECT LOGIC ---
        # ==========================================
        for obj in current_objects:
            obj_id = obj["id"]
            obj_center = obj["center"]

            if obj_id not in scene_memory:
                scene_memory[obj_id] = {
                    "class": obj["class"], "center": obj_center, "box": obj["box"],
                    "logged_this_event": False, "motion_frames": 0, "static_frames": 0,
                    "is_armed": False, "occluded_frames": 0
                }
                continue

            mem = scene_memory[obj_id]
            mem["box"] = obj["box"]
            dist_moved = calculate_distance(mem["center"], obj_center)

            if dist_moved <= MOVEMENT_THRESHOLD:
                mem["motion_frames"] = 0
                mem["static_frames"] += 1
                if mem["static_frames"] >= FRAMES_TO_ARM and not mem["is_armed"]:
                    mem["is_armed"] = True
                    mem["center"] = obj_center
                    print(f"🛡️ [{camera_name}] {mem['class']} rested for 10s. Now armed.")
            else:
                mem["static_frames"] = 0
                if mem["is_armed"]:
                    mem["motion_frames"] += 1
                    if mem["motion_frames"] >= FRAMES_TO_CONFIRM_MOTION and not mem["logged_this_event"]:

                        # Find exactly WHO picked it up based on highest intersection area
                        best_p_id = None
                        highest_ioa = OVERLAP_REQUIRED

                        for p_id, p_box in current_persons.items():
                            ioa = calculate_ioa(p_box, obj["box"])
                            if ioa > highest_ioa:
                                highest_ioa = ioa
                                best_p_id = p_id

                        if best_p_id is not None:
                            print(f"📦 [{camera_name}] Track {best_p_id} moved {mem['class']} (IoA: {highest_ioa:.2f})")
                            active_sessions[best_p_id]["pending_objects"].append(mem["class"])
                            mem["logged_this_event"] = True
                            mem["is_armed"] = False

                mem["center"] = obj_center

        # Grace Period Cleanup & Vanish Detection
        current_object_ids = [o["id"] for o in current_objects]
        stale_ids = []

        for memory_id, mem in scene_memory.items():
            if memory_id not in current_object_ids:
                if mem["occluded_frames"] == 0 and mem["is_armed"] and not mem["logged_this_event"]:

                    # Find who was closest when it suddenly vanished
                    best_p_id = None
                    highest_ioa = 0.05
                    for p_id, p_box in current_persons.items():
                        ioa = calculate_ioa(p_box, mem["box"])
                        if ioa > highest_ioa:
                            highest_ioa = ioa
                            best_p_id = p_id

                    if best_p_id is not None:
                        print(f"🪄📦 [{camera_name}] Track {best_p_id} grabbed vanishing {mem['class']}")
                        active_sessions[best_p_id]["pending_objects"].append(mem["class"])
                        mem["logged_this_event"] = True
                        mem["is_armed"] = False

                mem["occluded_frames"] += 1
                if mem["occluded_frames"] >= FRAMES_TO_FORGET:
                    stale_ids.append(memory_id)
            else:
                mem["occluded_frames"] = 0

        for stale_id in stale_ids:
            del scene_memory[stale_id]

        # ==========================================
        # --- 3. MULTI-AGENT EVENT END LOGIC ---
        # ==========================================
        departed_track_ids = []

        for p_id, session in active_sessions.items():
            if p_id not in current_persons:
                session["frames_since_last_seen"] += 1

                # Person has been gone longer than the post-roll buffer size
                if session["frames_since_last_seen"] >= buffer_size:
                    departed_track_ids.append(p_id)

        for p_id in departed_track_ids:
            session = active_sessions.pop(p_id)
            session["video_queue"].put(None)  # Kill their specific writer thread

            # Ghost filter check
            if session["visible_frames_count"] < (fps / 2):
                print(f"👻 [{camera_name}] Ghost track {p_id} discarded. (False Positive)")
                session["video_thread"].join()
                if os.path.exists(session["temp_filename"]):
                    os.remove(session["temp_filename"])
                continue

            if not session["alert_sent"] and session["match_id"] is None:
                alert_queue.put({
                    "type": "alert", "user_id": user_id, "person_id": None,
                    "camera_id": camera_id, "camera_name": camera_name,
                    "person_name": "Identity Unconfirmed", "timestamp": datetime.now().isoformat()
                })

            safe_name = session["match_name"].replace(" ", "_")
            final_filename = f"{safe_name}_{session['event_timestamp']}_tr{p_id}.mp4"

            if session["match_type"] == "FAMILY":
                final_path = os.path.join(FAMILY_DIR, final_filename)
                db_video_path = f"media/events/family/{final_filename}"
            else:
                final_path = os.path.join(UNWANTED_DIR, final_filename)
                db_video_path = f"media/events/unwanted/{final_filename}"

            session["video_thread"].join()
            shutil.move(session["temp_filename"], final_path)
            print(f"🛑 [{camera_name}] Track {p_id} ended. Saved: {final_path}")

            db_event_string = f"{session['match_type'].lower()}_detected"
            if is_private:
                db_video_path = ""

            # Commit primary event to the database specifically for THIS person
            event_id = log_event_start(
                user_id=user_id, camera_id=camera_id, person_id=session["match_id"],
                event_type=db_event_string, video_path=db_video_path, detected_at=str(session["start_time"])
            )

            # Log ONLY the objects THIS specific person picked up
            if event_id:
                for obj_name in set(session["pending_objects"]):  # Set removes duplicates
                    log_object_interaction(event_log_id=event_id, object_name=obj_name)

            log_event_end(event_id)