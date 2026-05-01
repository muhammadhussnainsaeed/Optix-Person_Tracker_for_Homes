import multiprocessing
import queue
from sqlalchemy import text

# Import your DB and AI tools
from db.session import SessionLocal
from ai_engine.face_recognition import FaceCache
from ai_engine.vision_worker import camera_worker_process


class CameraOrchestrator:
    def __init__(self):
        self.active_workers = {}
        self.alert_queue = None  # <-- 1. Add this to hold the queue globally

    def set_alert_queue(self, q):
        """Saves the alert queue into the orchestrator's memory."""
        self.alert_queue = q

    def sync_cameras(self):  # <-- 2. Remove alert_queue from here
        """Starts/Stops cameras based on the database."""
        db = SessionLocal()
        try:
            db_cameras = db.execute(text("SELECT id, user_id, video_url, name FROM cameras")).fetchall()
            desired_state = {str(c.id): {"url": c.video_url, "user_id": str(c.user_id), "name": c.name} for c in
                             db_cameras}

            # 1. Kill old/changed cameras
            for cam_id, data in list(self.active_workers.items()):
                if cam_id not in desired_state or desired_state[cam_id]["url"] != data["url"]:
                    print(f"🛑 [ORCHESTRATOR] Stopping worker for Camera {cam_id[-4:]}")
                    data["process"].terminate()
                    data["process"].join()
                    del self.active_workers[cam_id]

            # 2. Boot new cameras and give them a Command Queue
            for cam_id, cam_data in desired_state.items():
                if cam_id not in self.active_workers or not self.active_workers[cam_id]["process"].is_alive():
                    print(f"🚀 [ORCHESTRATOR] Booting new AI Worker for {cam_data['name']}...")

                    initial_user_cache = FaceCache.get_user_cache(cam_data["user_id"])
                    cmd_queue = multiprocessing.Queue()

                    p = multiprocessing.Process(
                        target=camera_worker_process,
                        args=(cam_id, cam_data["name"], cam_data["url"], cam_data["user_id"], initial_user_cache,
                              self.alert_queue, cmd_queue),  # <-- 3. Use self.alert_queue here!
                        name=f"CamWorker-{cam_id[-4:]}"
                    )
                    p.start()

                    self.active_workers[cam_id] = {
                        "process": p,
                        "url": cam_data["url"],
                        "cmd_queue": cmd_queue
                    }
        except Exception as e:
            print(f"❌ [ORCHESTRATOR] Sync Error: {e}")
        finally:
            db.close()

    def broadcast_reload_faces(self, user_id: str):
        """API calls this to tell all running cameras to update their memory."""
        print(f"📬 [ORCHESTRATOR] Sending RELOAD signal to User {user_id[-4:]}'s cameras...")
        for cam_id, data in self.active_workers.items():
            try:
                data["cmd_queue"].put_nowait({
                    "action": "RELOAD_FACES",
                    "user_id": user_id
                })
            except queue.Full:
                pass

    def shutdown_all(self):
        print("🛑 [ORCHESTRATOR] Shutting down all AI workers...")
        for cam_id, data in self.active_workers.items():
            data["process"].terminate()
            data["process"].join()
        print("✅ All GPU memory released.")


# Create the single, global instance right here
camera_manager = CameraOrchestrator()