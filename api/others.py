from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core import security
from db import session
from schemas import user

router = APIRouter(tags=["Others"])

@router.get("/others/get_all_persons")
def get_all_persons(user_id: str, username: str, jwt_token: str, db: Session = Depends(session.get_db)):
    # 1. Verify JWT Token
    token_verification = security.verify_token(jwt_token)

    if username != token_verification:
        raise HTTPException(status_code=401, detail="Verification Failed")

    # 2. Query Construction
    # This query uses a Scalar Subquery to grab the 'is_primary' photo.
    # If no primary exists, it will return NULL for that column.
    query = text("""
                 SELECT p.id,
                        p.name,
                        p.person_type,
                        (SELECT pp.photo_url
                         FROM person_photos pp
                         WHERE pp.person_id = p.id
                           AND pp.is_primary = TRUE
                            LIMIT 1 ) AS primary_photo
                 FROM persons p
                 WHERE p.user_id = :user_id
                 ORDER BY name ASC
                 """)

    result = db.execute(query, {"user_id": user_id})
    persons_list = result.mappings().all()

    return {
        "message": "Persons fetched successfully",
        "data": persons_list
    }

@router.get("/others/get_all_family")
def get_all_family(user_id: str, username: str, jwt_token: str, db: Session = Depends(session.get_db)):
    # 1. Verify JWT Token
    token_verification = security.verify_token(jwt_token)

    if username != token_verification:
        raise HTTPException(status_code=401, detail="Verification Failed")

    # 2. Query Construction
    # We join 'persons' with 'family_members' to get the relationship field.
    # We use the same scalar subquery logic for the primary photo.
    query = text("""
        SELECT 
            p.id, 
            p.name,
            f.relationship,
            (
                SELECT pp.photo_url 
                FROM person_photos pp 
                WHERE pp.person_id = p.id 
                AND pp.is_primary = TRUE 
                LIMIT 1
            ) AS primary_photo
        FROM persons p
        JOIN family_members f ON p.id = f.person_id
        WHERE p.user_id = :user_id 
          AND p.person_type = 'FAMILY'
        ORDER BY name ASC
    """)

    result = db.execute(query, {"user_id": user_id})
    family_list = result.mappings().all()

    return {
        "message": "Family members fetched successfully",
        "data": family_list
    }

