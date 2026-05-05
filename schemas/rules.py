from pydantic import BaseModel
from uuid import UUID
from datetime import time
from typing import List, Optional

# Define the structure of the incoming data for creating a rule
class MonitoringRuleCreateRequest(BaseModel):
    rule_name: str
    person_id: str
    user_id: str
    username: str
    jwt_token: str
    camera_ids: List[str]
    from_time: Optional[str] = None  # Frontend sends "22:00:00" string, Pydantic converts to time object
    to_time: Optional[str] = None
    is_active: bool = True


# Input for Delete Operation
class MonitoringRuleDeleteRequest(BaseModel):
    username: str
    jwt_token: str
    user_id: str
    rule_id: str

# Input for Update Operation
class MonitoringRuleUpdateRequest(BaseModel):
    username: str
    jwt_token: str
    user_id: str
    rule_id: str
    rule_name: str
    camera_id: List[str] = None
    person_id: str
    from_time: Optional[str] = None
    to_time: Optional[str] = None
    is_active: bool

class MonitoringRuleToggleRequest(BaseModel):
    username: str
    jwt_token: str
    user_id: str
    rule_id: str
    is_active: bool