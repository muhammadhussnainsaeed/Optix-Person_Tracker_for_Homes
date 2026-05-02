from dateutil import parser
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from core import security
from db import session
from schemas import logs

router = APIRouter(tags=["Logs"])

@router.get("/logs/unwanted_person/fetch_all")
def fetch_list(username: str,jwt_token: str, user_id: str, db: Session = Depends(session.get_db)):

    token_verification= security.verify_token(jwt_token)

    if username != token_verification:
        raise HTTPException(status_code=400, detail="Verification Failed")

    query = text("""
            SELECT 
    el.id AS log_id, 
    el.detected_at,
    el.exited_at,
    el.snapshot_url,

    COALESCE(p.name, 'Identity Unconfirmed') AS person_name,
    COALESCE(p_p.photo_url, '') AS person_photo,

    c.location AS room_name,
    f.title AS floor_title,

    (
        SELECT json_agg(
            json_build_object(
                'object_name', oi.object_name,
                'moved_at', oi.moved_at
            )
        )
        FROM object_interactions oi
        WHERE oi.event_log_id = el.id
    ) AS interactions

FROM event_logs el

LEFT JOIN persons p ON el.person_id = p.id
LEFT JOIN person_photos p_p ON p.id = p_p.person_id AND p_p.is_primary = true
LEFT JOIN cameras c ON el.camera_id = c.id
LEFT JOIN floors f ON c.floor_id = f.id

WHERE el.user_id = :user_id
  AND el.event_type = 'unwanted_detected'

ORDER BY el.detected_at DESC
        """)

    result = db.execute(query, {"user_id": user_id})
    logs = result.mappings().all()

    return {
        "message": "Unwanted logs fetched successfully",
        "logs": logs
    }

@router.get("/logs/family_member/fetch_all")
def fetch_list(username: str,jwt_token: str, user_id: str, db: Session = Depends(session.get_db)):

    token_verification= security.verify_token(jwt_token)

    if username != token_verification:
        raise HTTPException(status_code=400, detail="Verification Failed")

    query = text("""
            SELECT 
                el.id AS log_id,
                el.detected_at,
                el.exited_at,
                el.snapshot_url,             -- e.g. "Unknown Person detected..."
                p.name AS person_name,      -- e.g. "Unknown" or a name if you tagged them later
				p_p.photo_url AS person_photo,
                c.location AS room_name,
                f.title AS floor_title,
				(
    SELECT json_agg(
        json_build_object(
            'object_name', oi.object_name, 
            -- Cast to text to replace the 'T' with a space natively in PostgreSQL
            'moved_at', oi.moved_at
        )
    )
    FROM object_interactions oi
    WHERE oi.event_log_id = el.id
) AS interactions
            FROM event_logs el
            JOIN persons p ON el.person_id = p.id
			LEFT JOIN person_photos p_p ON p.id = p_p.person_id
            LEFT JOIN cameras c ON el.camera_id = c.id
            LEFT JOIN floors f ON c.floor_id = f.id
            WHERE el.user_id = :user_id
              AND el.event_type = 'family_detected' AND p_p.is_primary= true
            ORDER BY el.detected_at DESC
        """)

    result = db.execute(query, {"user_id": user_id})
    logs = result.mappings().all()
    return {
        "message": "Family logs fetched successfully",
        "logs": logs
    }

@router.post("/logs/investigate")
def investigate(user_data: logs.InvestigateRequest, db: Session = Depends(session.get_db)):

    token_verification = security.verify_token(user_data.jwt_token)

    if user_data.username != token_verification:
        raise HTTPException(status_code=400, detail="Verification Failed")

    if str(user_data.starting_time) == "None":
        user_data.starting_time = None
    if str(user_data.ending_time) == "None":
        user_data.ending_time = None

    base_query = """
            SELECT 
                el.id AS log_id,
                el.detected_at,
                el.exited_at,
                el.snapshot_url,
                el.event_type AS event_type,
                p.name AS person_name,
				p_p.photo_url AS person_photo,
                c.location AS room_name,
                f.title AS floor_title,
				(
        SELECT json_agg(
            json_build_object(
                'object_name', oi.object_name, 
                'moved_at', oi.moved_at
            )
        )
        FROM object_interactions oi
        WHERE oi.event_log_id = el.id
    ) AS interactions
            FROM event_logs el
            LEFT JOIN persons p ON el.person_id = p.id
			LEFT JOIN person_photos p_p ON p.id = p_p.person_id
            LEFT JOIN cameras c ON el.camera_id = c.id
            LEFT JOIN floors f ON c.floor_id = f.id
            WHERE el.user_id = :user_id AND p_p.is_primary= true
        """

    # Dictionary to hold parameters
    query_params = {"user_id": user_data.user_id}

    # 3. Apply Filters Dynamically

    # A. Filter by Type
    if user_data.type == "Family":
        base_query += " AND el.event_type = 'family_detected'"
    elif user_data.type == "Unwanted":
        base_query += " AND el.event_type = 'unwanted_detected'"

    # B. Filter by Camera
    if user_data.camera_id and user_data.camera_id != "All":
        base_query += " AND el.camera_id = :cid"
        query_params["cid"] = user_data.camera_id

    # C. Filter by Time
    try:
        # Now this logic works correctly because ending_time is actually None
        if user_data.starting_time and user_data.ending_time:
            # Case 1: Both provided
            start_dt = parser.parse(str(user_data.starting_time))
            end_dt = parser.parse(str(user_data.ending_time))
            base_query += " AND el.detected_at BETWEEN :start AND :end"
            query_params["start"] = start_dt
            query_params["end"] = end_dt

        elif user_data.starting_time:
            # Case 2: Start Only (This will now run correctly for your input)
            start_dt = parser.parse(str(user_data.starting_time))
            base_query += " AND el.detected_at >= :start"
            query_params["start"] = start_dt

        elif user_data.ending_time:
            # Case 3: End Only
            end_dt = parser.parse(str(user_data.ending_time))
            base_query += " AND el.detected_at <= :end"
            query_params["end"] = end_dt

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    # 4. Sorting
    base_query += " ORDER BY el.detected_at DESC"

    # 5. Execute
    result = db.execute(text(base_query), query_params)
    logs = result.mappings().all()

    return {
        "message": "Investigation logs fetched successfully",
        "logs": logs
    }

@router.get("/logs/unwanted_person/details")
def log_unwanted_person_details(username: str, user_id: str, jwt_token: str, log_id: str, db: Session = Depends(session.get_db)):

    token_verification = security.verify_token(jwt_token)
    if username != token_verification:
        raise HTTPException(status_code=400, detail="Verification Failed")

    # 2. Step 1: Get the Person ID from the provided Log ID
    # We only need the person_id here to know WHO we are looking for.
    query_find_person = text("""
        SELECT person_id
        FROM event_logs
        WHERE id = :log_id AND user_id = :user_id
    """)

    row = db.execute(query_find_person, {"log_id": log_id, "user_id": user_id}).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Log not found")

    target_person_id = row[0]  # Extract the UUID

    # 3. Step 2: Fetch ALL logs for that Person
    # Now we get the full list (history) for this specific unwanted person.
    query_all_logs = text("""
        SELECT
           el.id AS log_id,
            el.detected_at,
            el.exited_at,
            el.snapshot_url,             -- e.g. "Unknown Person detected..."
            p.name AS person_name,      -- e.g. "Unknown" or a name if you tagged them later
			p_p.photo_url AS person_photo,
            c.location AS room_name,
            f.title AS floor_title,
            (
    SELECT json_agg(
        json_build_object(
            'object_name', oi.object_name,
            'moved_at', oi.moved_at
        )
    )
    FROM object_interactions oi
    WHERE oi.event_log_id = el.id
) AS interactions
        FROM event_logs el
        JOIN persons p ON el.person_id = p.id
        LEFT JOIN person_photos p_p ON p.id = p_p.person_id
        LEFT JOIN cameras c ON el.camera_id = c.id
        LEFT JOIN floors f ON c.floor_id = f.id
        WHERE el.person_id = :person_id AND el.id != :log_id
        ORDER BY el.detected_at DESC
    """)

    result_logs = db.execute(query_all_logs, {"person_id": target_person_id, "log_id": log_id})
    all_logs_list = result_logs.mappings().all()

    # 4. Return the List
    return {
        "message": "Unwanted person history fetched successfully",
        "logs": all_logs_list
    }

# @router.get("/logs/family_member/details")
# def log_family_member_details(username: str, jwt_token: str, log_id: str, db: Session = Depends(session.get_db)):
#
#     token_verification = security.verify_token(jwt_token)
#
#     if username != token_verification:
#         raise HTTPException(status_code=400, detail="Verification Failed")
#
#     query = text("""
#             SELECT
#                 el.id AS log_id,
#                 el.detected_at,
#                 el.exited_at,
#                 el.snapshot_url,
#                 p.id AS person_id,
#                 p.name AS person_name,
#                 fm.relationship,
#                 ph.photo_url AS profile_photo,
#                 c.location AS room_name,
#                 f.title AS floor_title
#             FROM event_logs el
#             JOIN persons p ON el.person_id = p.id
#             LEFT JOIN family_members fm ON p.id = fm.person_id
#             LEFT JOIN person_photos ph ON p.id = ph.person_id AND ph.is_primary = TRUE
#             LEFT JOIN cameras c ON el.camera_id = c.id
#             LEFT JOIN floors f ON c.floor_id = f.id
#             WHERE el.id = :lid
#         """)
#
#     result = db.execute(query, {"lid": log_id})
#     row = result.mappings().fetchone()
#
#     # 3. Handle Not Found
#     if not row:
#         raise HTTPException(status_code=404, detail="Log not found")
#
#     # 4. Return Structured Data
#     return {
#         "message": "Log details fetched successfully",
#         "log_info": {
#             "id": str(row["log_id"]),
#             "detected_at": str(row["detected_at"]),
#             "exited_at": str(row["exited_at"]) if row["exited_at"] else "Ongoing",
#             "snapshot_url": row["snapshot_url"]
#         },
#         "person_info": {
#             "id": str(row["person_id"]),
#             "name": row["person_name"],
#             "relationship": row["relationship"] or "Unknown",
#             "profile_photo": row["profile_photo"] or ""
#         },
#         "location_info": {
#             "room": row["room_name"] or "Unknown Room",
#             "floor": row["floor_title"] or "Unknown Floor"
#         }
#     }
#