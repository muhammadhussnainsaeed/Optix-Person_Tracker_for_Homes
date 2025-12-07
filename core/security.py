import jwt
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from uuid import UUID
from typing import Union
from passlib.context import CryptContext

# --- CONFIG ---
SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 36000

# For Password Hashing
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# --- 1. Create Token (With +5 Offset) ---
def create_access_token(subject: Union[str, UUID], expires_delta: int = ACCESS_TOKEN_EXPIRE_MINUTES):
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
    if isinstance(subject, UUID):
        subject = str(subject)

    to_encode = {
        "sub": subject,
        "exp": expire,
        "iat": now_pkt  # Issued At (Shows +05:00 in the timestamp)
    }

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# --- 2. Verify Token ---
def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing subject (sub)."
            )
        return user_id

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


# --- TEST ---
# token = create_access_token(subject="ali_123")
# print(f"Token: {token}")
#
# # Just to show you the time it is using:
# pk_offset = timezone(timedelta(hours=5))
# print(f"Server Time used: {datetime.now(pk_offset)}")