from typing import Dict, Any

from pydantic import BaseModel


class Create_Floor(BaseModel):
    user_id: str
    username: str
    title: str
    description: str
    jwt_token: str

class Update_Floor(BaseModel):
    user_id: str
    username: str
    floor_id: str
    title: str
    description: str
    jwt_token: str

class Delete_Floor(BaseModel):
    user_id: str
    username: str
    floor_id: str
    jwt_token: str

class CreateFloorPlan(BaseModel):
    user_id: str
    username: str
    floor_id: str
    jwt_token: str
    plan_data: Dict[str, Any]

class UpdateFloorPlan(BaseModel):
    user_id: str
    username: str
    floor_id: str
    jwt_token: str
    plan_data: Dict[str, Any]

class GetFloorPlan(BaseModel):
    user_id: str
    username: str
    floor_id: str
    jwt_token: str