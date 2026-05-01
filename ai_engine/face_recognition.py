import numpy as np
from deepface import DeepFace
from scipy.spatial.distance import cosine
from sqlalchemy import text
from db.session import SessionLocal
from config import FACE_MATCH_THRESHOLD


class FaceCache:
    """Singleton to hold in-memory user facial embeddings and camera mappings."""
    _user_cache = {}
    _camera_cache = {}

    @classmethod
    def sync_from_db(cls):
        print("🔄 [SYNC] Fetching user faces and cameras...")
        db = SessionLocal()
        try:
            # 1. Map Cameras to Users
            cameras = db.execute(text("SELECT id, user_id, video_url FROM cameras")).fetchall()
            cls._camera_cache = {str(c.id): {"user_id": str(c.user_id), "video_url": c.video_url} for c in cameras}

            # 2. Fetch all photos grouped by person
            raw_query = text("""
                SELECT p.user_id, p.id AS person_id, p.name, p.person_type, pp.photo_url
                FROM persons p
                JOIN person_photos pp ON p.id = pp.person_id
            """)
            results = db.execute(raw_query).fetchall()

            person_data = {}
            for row in results:
                uid, pid = str(row.user_id), str(row.person_id)
                person_data.setdefault(uid, {}).setdefault(pid,
                                                           {"name": row.name, "type": row.person_type, "photos": []})
                person_data[uid][pid]["photos"].append(row.photo_url)

            # 3. Generate Centroid Embeddings
            cls._user_cache.clear()
            for uid, persons in person_data.items():
                cls._user_cache[uid] = {}
                for pid, data in persons.items():
                    embeddings = []
                    for photo_path in data["photos"]:
                        try:
                            rep = \
                            DeepFace.represent(img_path=photo_path, model_name="ArcFace", enforce_detection=False)[0]
                            embeddings.append(rep["embedding"])
                        except Exception as e:
                            print(f"⚠️ [SYNC] Failed processing {photo_path}: {e}")

                    if embeddings:
                        cls._user_cache[uid][pid] = {
                            "name": data["name"],
                            "type": data["type"],
                            "embedding": np.mean(embeddings, axis=0)  # Average the 3 photos
                        }
            print("✅ [SYNC] In-memory embedding cache updated.")
        finally:
            db.close()

    @classmethod
    def get_user_cache(cls, user_id: str):
        return cls._user_cache.get(user_id, {})

    @classmethod
    def get_all_cameras(cls):
        return cls._camera_cache


def identify_face(face_crop, user_specific_cache: dict):
    """Compares a cropped face against a specific user's pre-calculated embeddings."""
    if not user_specific_cache:
        return "Unknown", None, "unwanted_detected"

    try:
        target_embedding = DeepFace.represent(img_path=face_crop, model_name="ArcFace", enforce_detection=False)[0][
            "embedding"]

        best_match_name, best_match_id, best_match_type = "Unknown", None, "unwanted_detected"
        lowest_dist = 1.0

        for pid, data in user_specific_cache.items():
            dist = cosine(data["embedding"], target_embedding)
            if dist < FACE_MATCH_THRESHOLD and dist < lowest_dist:
                lowest_dist = dist
                best_match_name = data["name"]
                best_match_id = pid
                best_match_type = data["type"]

        return best_match_name, best_match_id, best_match_type
    except Exception:
        return "Unknown", None, "unwanted_detected"