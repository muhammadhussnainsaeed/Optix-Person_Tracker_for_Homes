import json


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session


from core import security
from db import session
from schemas import floor
from schemas.floor import Update_Floor, Delete_Floor


router = APIRouter(tags=["Floor"])


@router.get("/floor/fetch_all")
def fetch_list(username: str,jwt_token: str, user_id: str, db: Session = Depends(session.get_db)):


   token_verification= security.verify_token(jwt_token)


   if username != token_verification:
       raise HTTPException(status_code=400, detail="Verification Failed")


   query = text("""
       SELECT id, title, description
       FROM floors
       WHERE user_id = :user_id
   """)


   result = db.execute(query, {"user_id": user_id})
   floors = result.mappings().all()


   return {
       "message": "Floor list fetched successfully",
       "count": len(floors),
       "Floors": floors
   }


@router.post("/floor/add")
def add_floor(user_data: floor.Create_Floor, db: Session = Depends(session.get_db)):
   token_verification = security.verify_token(user_data.jwt_token)


   if user_data.username != token_verification:
       raise HTTPException(status_code=400, detail="Verification Failed")


   query = text("""
       INSERT INTO floors (
           user_id,
           title,
           description
       )
       VALUES (
           :user_id,
           :title,
           :description
       )
       RETURNING id, title
   """)


   result = db.execute(query, {
       "user_id": user_data.user_id,
       "title": user_data.title,
       "description": user_data.description
   })


   result = result.fetchone()
   db.commit()


   return {
       "message": "Floor Added successfully",
       "id": result[0],
       "title": result[1]
   }


@router.put("/floor/update")
def update_floor(user_data: Update_Floor, db: Session = Depends(session.get_db)):
   # 1. Verify JWT Token
   token_verification = security.verify_token(user_data.jwt_token)


   if user_data.username != token_verification:
       raise HTTPException(status_code=401, detail="Verification Failed")


   # 2. Define the UPDATE Query
   # We filter by floor_id AND user_id to ensure the user owns this floor
   query = text("""
                UPDATE floors
                SET title       = :title,
                    description = :description
                WHERE id = :floor_id
                  AND user_id = :user_id RETURNING id, title
                """)


   # 3. Execute the Query
   result = db.execute(query, {
       "floor_id": user_data.floor_id,
       "user_id": user_data.user_id,
       "title": user_data.title,
       "description": user_data.description
   })


   updated_row = result.fetchone()


   # 4. Check if the update actually happened
   if not updated_row:
       # This triggers if the ID is wrong or belongs to another user
       db.rollback()
       raise HTTPException(
           status_code=404,
           detail="Floor not found or you do not have permission to edit it"
       )


   db.commit()


   return {
       "message": "Floor updated successfully",
       "id": updated_row[0],
       "title": updated_row[1]
   }


@router.delete("/floor/delete")
def delete_floor(user_data: Delete_Floor, db: Session = Depends(session.get_db)):
    # 1. Verify JWT Token
    token_verification = security.verify_token(user_data.jwt_token)
    if user_data.username != token_verification:
        raise HTTPException(status_code=401, detail="Verification Failed")

    try:
        # 0. Delete object_interactions linked to this floor's event logs
        # We nest the subqueries: Interactions -> Logs -> Cameras -> Floor
        db.execute(text("""
                        DELETE
                        FROM object_interactions
                        WHERE event_log_id IN (SELECT id
                                           FROM event_logs
                                           WHERE camera_id IN (SELECT id FROM cameras WHERE floor_id = :f_id))
                        """), {"f_id": user_data.floor_id})

        # A. Delete event_logs linked to cameras on this floor
        db.execute(text("""
                        DELETE
                        FROM event_logs
                        WHERE camera_id IN (SELECT id FROM cameras WHERE floor_id = :f_id)
                        """), {"f_id": user_data.floor_id})

        # B. Delete camera_links associated with this floor's cameras
        db.execute(text("""
                        DELETE
                        FROM camera_links
                        WHERE camera_id_from IN (SELECT id FROM cameras WHERE floor_id = :f_id)
                           OR camera_id_to IN (SELECT id FROM cameras WHERE floor_id = :f_id)
                        """), {"f_id": user_data.floor_id})

        # C. Delete floor_plans associated with this floor
        db.execute(text("DELETE FROM floor_plans WHERE floor_id = :f_id"), {"f_id": user_data.floor_id})

        # D. Delete all cameras on this floor
        db.execute(text("DELETE FROM cameras WHERE floor_id = :f_id"), {"f_id": user_data.floor_id})

        # E. Finally, delete the floor itself and verify ownership
        result = db.execute(text("""
                                 DELETE
                                 FROM floors
                                 WHERE id = :f_id
                                   AND user_id = :u_id RETURNING id, title
                                 """), {"f_id": user_data.floor_id, "u_id": user_data.user_id})

        deleted_row = result.fetchone()

        # Verify if the floor actually existed and was owned by the user
        if not deleted_row:
            db.rollback()
            raise HTTPException(status_code=404, detail="Floor not found or unauthorized")

        db.commit()
        return {
            "message": "Floor and all associated cameras, logs, and plans deleted successfully",
            "id": deleted_row[0],
            "title": deleted_row[1]
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Transaction failed: {str(e)}")

@router.post("/floor/add_floor_data")
def add_floor_data(user_data: floor.CreateFloorPlan, db: Session = Depends(session.get_db)):
    token_verification = security.verify_token(user_data.jwt_token)

    if user_data.username != token_verification:
        raise HTTPException(status_code=400, detail="Verification Failed")

    json_data = json.dumps(user_data.plan_data)
    query = text("""
    INSERT INTO floor_plans (
            floor_id, 
            plan_data
        )
        VALUES (
            :floor_id, 
            :plan_data
        )
        RETURNING id
    """)

    result = db.execute(query, {
        "floor_id": user_data.floor_id,
        "plan_data": json_data
    })

    row = result.fetchone()
    db.commit()

    return {
        "message": "Floor plan created successfully!",
        "id": row[0]
    }

@router.put("/floor/update_floor_data")
def update_floor_data(user_data: floor.UpdateFloorPlan, db: Session = Depends(session.get_db)):
    token_verification = security.verify_token(user_data.jwt_token)

    if user_data.username != token_verification:
        raise HTTPException(status_code=400, detail="Verification Failed")

    json_data = json.dumps(user_data.plan_data)
    query = text("""
    UPDATE floor_plans 
        SET plan_data = :plan_data
        WHERE floor_id = :floor_id
        RETURNING id
    """)

    result = db.execute(query, {
        "floor_id": user_data.floor_id,
        "plan_data": json_data
    })

    result = result.fetchone()
    db.commit()

    return {
        "message": "Floor Plan Updated successfully",
        "id": result[0]
    }

@router.get("/floor/get_floor_data")
def get_floor_data(username: str,jwt_token: str, user_id: str, floor_id: str, db: Session = Depends(session.get_db)):
    user_data = floor.GetFloorPlan(
        username = username,
        user_id = user_id,
        jwt_token= jwt_token,
        floor_id= floor_id
    )
    # 1. Verify Token
    try:
        token_verification = security.verify_token(user_data.jwt_token)
        if user_data.username != token_verification:
            raise HTTPException(status_code=400, detail="Verification Failed")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Token")

    # 2. Define Query
    query = text("""
        SELECT plan_data 
        FROM floor_plans
        WHERE floor_id = :fid 
    """)

    # 3. Execute (Synchronous - No await)
    result = db.execute(query, {
        "fid": user_data.floor_id
    })

    row = result.fetchone()

    # 4. Handle Result
    if row is None:
        return {
            "message": "No plan found",
            "plan": ""
        }

    # 5. Return Data
    return {
        "message": "Floor Plan Fetched successfully",
        "plan": json.dumps(row[0]) or {}
    }