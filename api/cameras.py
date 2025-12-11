from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from db import session
from core import security
from schemas import camera

router = APIRouter(tags=["Camera"])

@router.get("/camera/fetch_all")
def fetch_list(username: str,jwt_token: str, user_id: str, db: Session = Depends(session.get_db)):

    token_verification= security.verify_token(jwt_token)

    if username != token_verification:
        raise HTTPException(status_code=400, detail="Verification Failed")

    query = text("""
        SELECT id, name, description, is_private
        FROM cameras 
        WHERE user_id = :user_id
    """)

    result = db.execute(query, {"user_id": user_id})
    cameras = result.mappings().all()

    return {
        "message": "Cameras fetched successfully",
        "count": len(cameras),
        "cameras": cameras
    }

@router.post("/camera/add")
def add_camera(user_data: camera.Create_Camera, db: Session = Depends(session.get_db)):
    token_verification = security.verify_token(user_data.jwt_token)

    if user_data.username != token_verification:
        raise HTTPException(status_code=400, detail="Verification Failed")

    query = text("""
        INSERT INTO cameras (
            user_id, 
            name, 
            location, 
            video_url, 
            description, 
            is_private,
            floor_id
        )
        VALUES (
            :user_id, 
            :name, 
            :location, 
            :video_url, 
            :description, 
            :is_private,
            :floor_id
        )
        RETURNING id, name, video_url
    """)

    result = db.execute(query, {
        "user_id": user_data.user_id,
        "name": user_data.name,
        "location": user_data.location,
        "video_url": user_data.video_url,
        "description": user_data.description,
        "is_private": user_data.is_private,
        "floor_id": user_data.floor_id
    })

    result = result.fetchone()
    db.commit()

    return {
        "message": "Camera Added successfully",
        "id": result[0],
        "name": result[1],
        "video_url": result[2]
    }

@router.get("/camera/details")
def camera_details(username: str,jwt_token: str, user_id: str, camera_id: str ,is_private: bool,db: Session = Depends(session.get_db)):
    user_data = camera.Camera_Detail(
        username=username,
        user_id=user_id,
        jwt_token=jwt_token,
        camera_id=camera_id,
        is_private= is_private
    )

    token_verification = security.verify_token(user_data.jwt_token)

    if user_data.username != token_verification:
        raise HTTPException(status_code=400, detail="Verification Failed")

    query = text("""
            SELECT id, name, location, description, video_url
            FROM cameras 
            WHERE id = :camera_id AND user_id = :user_id
        """)

    result = db.execute(query, {
        "camera_id": user_data.camera_id,
        "user_id": user_data.user_id
    })
    camera_detail = result.mappings().fetchone()

    final_video_url = camera_detail["video_url"]
    if is_private:
        final_video_url = None

    return {
        "message": "Camera Detail fetched successfully",
        "id": str(camera_detail["id"]),
        "name": camera_detail["name"],
        "location": camera_detail["location"],  # Matches your DB schema
        "description": camera_detail["description"],
        "video_url": final_video_url
    }