from pydantic import BaseModel

class AddFamilyMember(BaseModel):
    name: str
    relationship: str
    username: str
    jwt_token: str
    user_id: str

class GetFamilyDetails(BaseModel):
    user_id: str
    username: str
    jwt_tokens: str
    person_id: str