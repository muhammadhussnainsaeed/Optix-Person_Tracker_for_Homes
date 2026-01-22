from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from db import session
from core import security
router = APIRouter(tags=["Dashboard"])

@router.get("/dashboard/summary")
def fetch_list(username: str,jwt_token: str, user_id: str, db: Session = Depends(session.get_db)):

    token_verification= security.verify_token(jwt_token)

    if username != token_verification:
        raise HTTPException(status_code=400, detail="Verification Failed")

    query_counts = text("""
            SELECT COUNT(*) FROM cameras WHERE user_id = :user_id 
            UNION ALL
            SELECT COUNT(*) FROM persons WHERE user_id = :user_id AND person_type = 'FAMILY'
            UNION ALL
            SELECT COUNT(*) FROM event_logs 
            WHERE user_id = :user_id 
              AND event_type = 'unwanted_detected' 
              AND date(detected_at AT TIME ZONE 'Asia/Karachi') = CURRENT_DATE
        """)

    result = db.execute(query_counts, {"user_id": user_id})
    result_count = result.fetchall()

    cam_count = result_count[0][0] if len(result_count) > 0 else 0
    fam_count = result_count[1][0] if len(result_count) > 1 else 0
    alert_count = result_count[2][0] if len(result_count) > 2 else 0

    query_recent_family = text("""
             SELECT 
                el.id,                 
                el.detected_at,
                el.exited_at,
                el.snapshot_url, 
                p.name AS person_name,
				p_p.photo_url AS person_photo,
                c.location AS room_name,
                f.title AS floor_title
            FROM event_logs el
            JOIN persons p ON el.person_id = p.id
			LEFT JOIN person_photos p_p ON p.id = p_p.person_id
            LEFT JOIN cameras c ON el.camera_id = c.id
            LEFT JOIN floors f ON c.floor_id = f.id
            WHERE el.user_id = :user_id
              AND el.event_type = 'family_detected' AND p_p.is_primary= true
            ORDER BY el.detected_at DESC 
            LIMIT 1
        """)

    result2 = db.execute(query_recent_family, {"user_id": user_id})
    result_family_log = result2.fetchone()

    query_object_interation = text("""
            SELECT 
                object_name,moved_at,
                location_data
            FROM object_interactions
            WHERE event_log_id = :event_log_id
        """)

    if result_family_log:

        result4 = db.execute(query_object_interation, {"event_log_id": result_family_log[0]})
        result_family_log_object = result4.mappings().all()

        family_data = {
            "id": str(result_family_log[0]),
            "detected_at": str(result_family_log[1]) if result_family_log[1] else None,
            "exited_at": str(result_family_log[2]) if result_family_log[2] else None,
            "snapshot_url": result_family_log[3] or "",
            "name": result_family_log[4] or "Unknown",
            "person_photo": result_family_log[5] or "Unknown Person Photo",
            "room": result_family_log[6] or "Unknown Room",
            "floor": result_family_log[7] or "Unknown Floor",
            "object_interation": result_family_log_object
        }
    else:
        family_data = None

    query_recent_alert = text("""
             SELECT 
                el.id,                 
                el.detected_at,
                el.exited_at,
                el.snapshot_url, 
                p.name AS person_name,
				p_p.photo_url AS person_photo,
                c.location AS room_name,
                f.title AS floor_title
            FROM event_logs el
            JOIN persons p ON el.person_id = p.id
			LEFT JOIN person_photos p_p ON p.id = p_p.person_id
            LEFT JOIN cameras c ON el.camera_id = c.id
            LEFT JOIN floors f ON c.floor_id = f.id
            WHERE el.user_id = :user_id
              AND el.event_type = 'unwanted_detected' AND p_p.is_primary= true
            ORDER BY el.detected_at DESC 
            LIMIT 1
        """)

    result3 = db.execute(query_recent_alert, {"user_id": user_id})
    result_unwanted_log = result3.fetchone()

    if result_unwanted_log:

        result5 = db.execute(query_object_interation, {"event_log_id": result_unwanted_log[0]})
        result_unwanted_log_object = result5.mappings().all()

        unwanted_data = {
            "id": str(result_unwanted_log[0]) or "No id",
            "detected_at": str(result_unwanted_log[1]) if result_unwanted_log[1] else None,
            "exited_at": str(result_unwanted_log[2]) if result_unwanted_log[2] else None,
            "snapshot_url": result_unwanted_log[3] or "",
            "name": result_unwanted_log[4] or "Unknown",
            "person_photo": result_unwanted_log[5] or "Unknown Person Photo",
            "room": result_unwanted_log[6] or "Unknown Room",
            "floor": result_unwanted_log[7] or "Unknown Floor",
            "object_interation": result_unwanted_log_object
        }
    else:
        unwanted_data = None

    return {
        "message": "Dashboard fetched successfully",
        "camera_count": cam_count,
        "family_count": fam_count,
        "today_event_count": alert_count,
        "recent_family_log": family_data,
        "recent_unwanted_log": unwanted_data
    }
