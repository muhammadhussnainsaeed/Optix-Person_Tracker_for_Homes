from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from db import session
from core import security
import json
from schemas import floor

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
        RETURNING id, plan_data
    """)

    result = db.execute(query, {
        "floor_id": user_data.floor_id,
        "plan_data": json_data
    })

    row = result.fetchone()
    db.commit()

    saved_data = row[1]

    if saved_data is None:
        saved_data = {
            "walls": [],
            "windows": [],
            "cameras": [],
            "doors": []
        }

    return {
        "id": str(row[0]) or None,
        "plan_data": saved_data
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
        WHERE floor_id = :floor_plan_id
        RETURNING id
    """)

    result = db.execute(query, {
        "floor_plan_id": user_data.floor_plan_id,
        "plan_data": json_data
    })

    result = result.fetchone()
    db.commit()

    return {
        "message": "Floor Plan Updated successfully",
        "id": result[0]
    }

@router.get("/floor/get_floor_data")
def get_floor_data(username: str,jwt_token: str, user_id: str, floor_plan_id: str, db: Session = Depends(session.get_db)):
    user_data = floor.GetFloorPlan(
        username = username,
        user_id = user_id,
        jwt_token= jwt_token,
        floor_plan_id= floor_plan_id
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
        SELECT id, plan_data 
        FROM floor_plans
        WHERE floor_id = :fid 
    """)

    # 3. Execute (Synchronous - No await)
    result = db.execute(query, {
        "fid": user_data.floor_plan_id
    })

    row = result.fetchone()

    print("hi",row)
    # 4. Handle Result
    if row is None:
        return {
            "message": "No plan found",
            "id": None,
            "plan": {
                "walls": [],
                "windows": [],
                "cameras": [],
                "doors": []
            }
        }

    # 5. Return Data
    return {
        "message": "Floor Plan Fetched successfully",
        "id": str(row[0]),
        "plan": row[1] or {}
    }