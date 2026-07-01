from pydantic import BaseModel, field_validator
from typing import Optional


class TokenRequest(BaseModel):
    api_key: str


class UpsertUserRequest(BaseModel):
    # Matches Project 1's UserDetails model exactly
    user_id: str
    name: str
    age: int
    gender: str
    city: str


class UserMessage(BaseModel):
    # Matches Project 1's UserMessage model exactly
    user_id: str
    session_id: str
    name: str
    age: int
    gender: str
    city: str
    incoming_message: str

    @field_validator("incoming_message")
    @classmethod
    def message_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError("incoming_message must not be empty")
        return v.strip()


class FeedbackUpdate(BaseModel):
    # Matches Project 1's FeedbackUpdate model exactly
    # message_id is a string and user_feedback is -1 or 1
    message_id: str
    user_feedback: int

    @field_validator("user_feedback")
    @classmethod
    def feedback_must_be_valid(cls, v):
        if v not in (-1, 1):
            raise ValueError("user_feedback must be -1 or 1")
        return v