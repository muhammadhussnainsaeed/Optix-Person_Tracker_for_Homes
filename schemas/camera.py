from pydantic import BaseModel

class Camera_Detail(BaseModel):
    camera_id: str
    username: str
    user_id: str
    jwt_token: str

class Create_Camera(BaseModel):
    user_id: str
    username: str
    name: str
    location: str
    video_url: str
    description: str
    is_private: bool
    jwt_token: str
    floor_id: str