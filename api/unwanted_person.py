from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from db import session
from core import security
from schemas import unwanted_person

router = APIRouter(tags=["Unwanted Person"])

@router.post("/unwanted/unmark")
def unmark_unwanted_person(user_data: unwanted_person.Unmark_Request,db: Session = Depends(session.get_db)):
    # 1. Security Verification
    token_verification = security.verify_token(user_data.jwt_token)

    if user_data.username != token_verification:
        raise HTTPException(status_code=400, detail="Verification Failed")
    find_log_query = text("""
                SELECT person_id 
                FROM event_logs 
                WHERE id = :lid
            """)

    result = db.execute(find_log_query, {"lid": user_data.log_id})
    log_row = result.fetchone()

    if not log_row:
        raise HTTPException(status_code=404, detail="Log not found")

    old_unwanted_id = log_row[0]

    # 3. Update the Log (The Migration)
    # - Change person_id to the Family Member's ID
    # - Change event_type to 'family_detected'
    update_query = text("""
                UPDATE event_logs 
                SET person_id = :fid,
                    event_type = 'family_detected'
                WHERE id = :lid
            """)

    db.execute(update_query, {
        "fid": user_data.family_id,
        "lid": user_data.log_id
    })

    # 4. Clean Up (Garbage Collection)
    # If the 'old_unwanted_id' has NO other logs left in the system,
    # it means that "Person" was a temporary glitch. We should delete them completely.
    # This keeps your 'persons' table clean of random 'Unknown' entries.

    if old_unwanted_id:
        # Check if any logs still point to this unwanted ID
        check_usage_query = text("""
                    SELECT COUNT(*) FROM event_logs WHERE person_id = :old_id
                """)
        usage_result = db.execute(check_usage_query, {"old_id": old_unwanted_id})
        count = usage_result.scalar()

        # If count is 0, DELETE the person (Cascade will remove their photos too)
        if count == 0:
            delete_person_query = text("DELETE FROM persons WHERE id = :old_id")
            db.execute(delete_person_query, {"old_id": old_unwanted_id})

    # 5. Commit Transaction
    db.commit()

    return {
        "message": "Person marked as Family Member successfully",
        "log_id": user_data.log_id,
        "new_person_id": user_data.family_id
    }