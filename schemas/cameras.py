from pydantic import BaseModel
import uuid

class Camera_List(BaseModel):
    name: str
    description: str
    privacy: bool


class Camera_Detail(BaseModel):
    name: str
    location: str
    video_url: str
    description: str
    privacy: bool

class Create_Camera(BaseModel):
    name: str
    location: str
    video_url: str
    description: str
    privacy: bool
    jwttoken: str
