from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import text
from db import session
from core import security
from schemas import user

router = APIRouter(tags=["Authentication"])

#Log_in API
@router.post("/auth/log_in")
def login(user_data: user.UserLogin, db: Session = Depends(session.get_db)):
    # Find user by username
    query = text("""
        SELECT id, username, name, hashed_password
        FROM users 
        WHERE username = :username
    """)

    result = db.execute(query, {"username": user_data.username})
    user_row = result.mappings().first()

    # Check if user exists and password is correct
    if not user_row or not security.verify_password(user_data.password, user_row["hashed_password"]):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    # Generate JWT token
    token = security.create_access_token(subject_id=user_row["id"], subject_username= user_data.username)

    return {
        "message": "Login successful",
        "id": str(user_row["id"]),
        "username": user_row["username"],
        "name": user_row["name"],
        "token": token
    }

#Sign_up API
@router.post("/auth/sign_up", status_code=201)
def register_user(user_data: user.UserSignup, db: Session = Depends(session.get_db)):
    # Check if username exists
    check_query = text("SELECT 1 FROM users WHERE username = :username")
    if db.execute(check_query, {"username": user_data.username}).fetchone():
        raise HTTPException(status_code=400, detail="Username already exists")

    # Hash password and security answer
    hashed_password = security.hash_password(user_data.password)
    hashed_answer = security.hash_password(user_data.security_answer)

    # Insert user
    insert_query = text("""
        INSERT INTO users (name, username, hashed_password, security_question, hashed_security_answer)
        VALUES (:name, :username, :hashed_password, :security_question, :hashed_answer)
        RETURNING id
    """)

    try:
        result = db.execute(insert_query, {
            "name": user_data.name,
            "username": user_data.username,
            "hashed_password": hashed_password,
            "security_question": user_data.security_question,
            "hashed_answer": hashed_answer
        })

        user_id = result.fetchone()[0]
        db.commit()

        return {
            "message": "User registered successfully",
            "id": str(user_id),
            "username": user_data.username
        }

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Registration failed - possible duplicate username")

    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

#Forget API
@router.post("/auth/reset_password")
def reset_password(user_data: user.UserForgetPassword, db: Session = Depends(session.get_db)):

    check_user_query = text("SELECT id,security_question,hashed_security_answer FROM users WHERE username = :username")

    result = db.execute(check_user_query, {"username": user_data.username}).fetchone()

    if not result:
        raise HTTPException(status_code=400, detail="Username not exists")


    if str(result[1]) != user_data.security_question or not security.verify_password(user_data.security_answer,result[2]):
        raise HTTPException(status_code=400, detail="Information Incorrect")

    hashed_password = security.hash_password(user_data.new_password)

    insert_query = text("""
        UPDATE users
        SET
            hashed_password = :hashed_password
        WHERE username = :username
            RETURNING id;
            """)

    try:
        result = db.execute(insert_query, {
            "username": user_data.username,
            "hashed_password": hashed_password
        })

        user_id = result.fetchone()[0]
        db.commit()

        return {
            "message": "User password updated successfully",
            "id": str(user_id),
            "username": user_data.username
        }
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Updating failed")

    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

