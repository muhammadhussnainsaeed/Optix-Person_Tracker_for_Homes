import jwt
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from uuid import UUID
from typing import Union
from passlib.context import CryptContext

# --- For Token ---
SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 86400

# For Password Hashing
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Create Token
def create_access_token(subject_id: Union[str, UUID],subject_username: str, expires_delta: int = ACCESS_TOKEN_EXPIRE_MINUTES):
    """
    Creates a JWT token using a manual UTC+5 (Pakistan) timezone.
    """
    # 1. Define the +5 Hour Offset Manually
    pk_offset = timezone(timedelta(hours=5))

    # 2. Get current time with that offset
    now_pkt = datetime.now(pk_offset)

    # 3. Calculate expiration
    expire = now_pkt + timedelta(minutes=expires_delta)

    # 4. Handle UUID conversion
    if isinstance(subject_id, UUID):
        subject = str(subject_id)

    to_encode = {
        "sub_id": subject,
        "sub_username": subject_username,
        "exp": expire,
        "iat": now_pkt  # Issued At (Shows +05:00 in the timestamp)
    }

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Verify Token ---
def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_username: str = payload.get("sub_username")

        if user_username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing subject (sub_username)."
            )
        return user_username

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired."
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials."
        )

# Function to hash passwords
def hash_password(password: str):
    return pwd_context.hash(password)

# Function to verify the password
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)
