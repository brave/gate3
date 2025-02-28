from enum import Enum

from pydantic import BaseModel


class HealthStatus(str, Enum):
    OK = "OK"
    KO = "KO"

class PingResponse(BaseModel):
    redis: HealthStatus
