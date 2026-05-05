import random
from sqlalchemy.orm import Session
from sqlalchemy import text
from db.session import SessionLocal
import uuid
import cv2
import os

def log_object_interaction(event_log_id: int, object_name: str):
    """Logs an object movement using raw SQL linked to the main event."""
    try:
        with SessionLocal() as db:
            query = text("""
                INSERT INTO object_interactions (event_log_id, object_name)
                VALUES (:event_log_id, :object_name)
            """)
            db.execute(query, {
                "event_log_id": event_log_id,
                "object_name": object_name
            })
            db.commit()
            print(f"📝 [DB] Logged Object Movement: {object_name} during Event {event_log_id}")
    except Exception as e:
        print(f"❌ [DB] Error logging object interaction: {e}")

def log_event_start(user_id: str, camera_id: str, person_id: str, event_type: str, video_path: str, detected_at: str) -> str:
    db: Session = SessionLocal()
    #event_id = str(uuid.uuid4())
    try:
        query = text("""
            INSERT INTO event_logs (user_id, camera_id, person_id, event_type, snapshot_url, detected_at)
            VALUES (:uid, :cid, :pid, :evt, :path, :detected_at)
            RETURNING id
        """)
        event_id = db.execute(query, {
            "uid": user_id,
            "cid": camera_id,
            "pid": person_id if person_id else None,
            "evt": event_type,
            "path": video_path,
            "detected_at": detected_at
        })
        db.commit()

        return event_id.fetchone()[0]
    except Exception as e:
        print(f"❌ [DB] Failed to log event start: {e}")
        db.rollback()
        return None
    finally:
        db.close()

def log_event_end(event_id: str):
    if not event_id: return
    db: Session = SessionLocal()
    try:
        query = text("UPDATE event_logs SET exited_at = NOW() WHERE id = :id")
        db.execute(query, {"id": event_id})
        db.commit()
    except Exception as e:
        print(f"❌ [DB] Failed to log event end: {e}")
        db.rollback()
    finally:
        db.close()

def update_event_identity(event_id: str, person_id: str, event_type: str):
    """Updates the event log mid-recording once a face is successfully recognized."""
    if not event_id: return
    db: Session = SessionLocal()
    try:
        query = text("""
            UPDATE event_logs 
            SET person_id = :pid, event_type = :evt 
            WHERE id = :id
        """)
        db.execute(query, {
            "id": event_id,
            "pid": person_id if person_id else None,
            "evt": event_type
        })
        db.commit()
    except Exception as e:
        print(f"❌ [DB] Failed to update event identity: {e}")
        db.rollback()
    finally:
        db.close()


def create_unknown_person(user_id: str, face_img):
    """Creates a new UNWANTED person in the DB with a random name and saves their photo."""
    db = SessionLocal()
    new_person_id = str(uuid.uuid4())
    photo_id = str(uuid.uuid4())

    save_dir = "media/persons"
    os.makedirs(save_dir, exist_ok=True)
    filename = f"{save_dir}/{new_person_id}.jpg"
    cv2.imwrite(filename, face_img)

    # 1. Generate the random UI name
    colors = [
        "Teal", "Azure", "Crimson", "Cobalt", "Amber",
        "Jade", "Onyx", "Ruby", "Silver", "Topaz"
    ]
    animals = [
        "Falcon", "Panda", "Wolf", "Tiger", "Bear",
        "Eagle", "Fox", "Hawk", "Panther", "Leopard"
    ]
    random_num = random.randint(100, 999)
    generated_name = f"{random.choice(colors)} {random.choice(animals)} {random_num}"

    try:
        # FIX: Use CAST(:var AS uuid) instead of :var::uuid to prevent SQLAlchemy syntax errors
        db.execute(text("""
            INSERT INTO persons (id, user_id, name, person_type) 
            VALUES (CAST(:pid AS uuid), CAST(:uid AS uuid), :name, 'UNWANTED')
        """), {"pid": new_person_id, "uid": user_id, "name": generated_name})

        db.execute(text("""
            INSERT INTO person_photos (id, person_id, photo_url, is_primary) 
            VALUES (CAST(:photoid AS uuid), CAST(:pid AS uuid), :url, TRUE)
        """), {"photoid": photo_id, "pid": new_person_id, "url": filename})

        db.commit()
        print(f"🆕 [DB] Created new profile for {generated_name}: {new_person_id}")

        # Return both so the AI worker can use the cool name in the WebSocket alert
        return new_person_id, generated_name

    except Exception as e:
        db.rollback()
        print(f"❌ [DB ERROR] Failed to create unknown person: {e}")
        return None, None
    finally:
        db.close()