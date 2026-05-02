from typing import Optional

from pydantic import BaseModel


class InvestigateRequest(BaseModel):
    user_id: str
    username: str
    jwt_token: str
    camera_id: Optional[str] = "All"
    type: Optional[str] = "All"
    starting_time: Optional[str] = None
    ending_time: Optional[str] = None


class IdentityCorrectionRequest(BaseModel):
    user_id: str
    username: str
    jwt_token: str
    event_id: str
    is_new_person: bool
    correct_person_id: Optional[str] = None