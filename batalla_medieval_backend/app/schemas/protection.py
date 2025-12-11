from pydantic import BaseModel


class ProtectionStatus(BaseModel):
    seconds_left: int
