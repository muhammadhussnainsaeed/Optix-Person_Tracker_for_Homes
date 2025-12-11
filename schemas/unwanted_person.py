from pydantic import BaseModel

class Unmark_Request(BaseModel):
    username: str
    jwt_token: str
    family_id: str