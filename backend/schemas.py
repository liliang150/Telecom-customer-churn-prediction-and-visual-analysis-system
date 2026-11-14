from typing import Any

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=128)


class SinglePredictRequest(BaseModel):
    record: dict[str, Any]


class TrainRequest(BaseModel):
    quick: bool = False


class VersionRequest(BaseModel):
    version: str


class DataConfirmRequest(BaseModel):
    saved_name: str = Field(min_length=1, max_length=255)
    kind: str = Field(pattern="^(train|predict)$")


def success(data: Any) -> dict:
    return {"code": 200, "message": "success", "data": data}
