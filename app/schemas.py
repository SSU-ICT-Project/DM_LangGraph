# schemas.
from pydantic import BaseModel
from typing import Optional

# 장소 정보를 담을 모델
class LocationInfo(BaseModel):
    placeName: str
    placeAddress: Optional[str] = None
    latitude: float
    longitude: float

# 프런트에서 받을 요청 모델
class AgentRequest(BaseModel):
    scheduleName: str
    scheduleStartTime: str
    scheduleEndTime: Optional[str] = None
    DepartureLocation: LocationInfo
    ArrivalLocation: LocationInfo
    test_mode: Optional[str] = None

# 우리가 최종적으로 반환할 응답 모델
class AgentResponse(BaseModel):
    recommendation: str