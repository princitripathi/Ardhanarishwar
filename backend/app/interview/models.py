from typing import Optional, Literal
from pydantic import BaseModel, field_validator
from datetime import datetime
import re

StatusType = Literal["scheduled", "active", "completed", "cancelled"]

class InterviewCreateRequest(BaseModel):
    candidate_name: str
    candidate_email: Optional[str] = None
    job_title: str
    job_description: str
    resume_text: str
    scheduled_date: str  # YYYY-MM-DD
    scheduled_time: str  # HH:MM
    duration_minutes: int

    @field_validator("candidate_name")
    @classmethod
    def validate_candidate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("candidate_name is required")
        if len(v.strip()) < 2:
            raise ValueError("candidate_name must be at least 2 characters")
        return v.strip()

    @field_validator("candidate_email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        v = v.strip()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("invalid email format")
        return v

    @field_validator("job_title")
    @classmethod
    def validate_job_title(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("job_title is required")
        return v.strip()

    @field_validator("job_description")
    @classmethod
    def validate_job_description(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("job_description is required")
        if len(v.strip()) < 10:
            raise ValueError("job_description must be at least 10 characters")
        return v.strip()

    @field_validator("resume_text")
    @classmethod
    def validate_resume(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("resume_text is required")
        if len(v.strip()) < 10:
            raise ValueError("resume_text must be at least 10 characters")
        return v.strip()

    @field_validator("scheduled_date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("scheduled_date is required")
        try:
            datetime.strptime(v.strip(), "%Y-%m-%d")
        except ValueError:
            raise ValueError("scheduled_date must be YYYY-MM-DD")
        return v.strip()

    @field_validator("scheduled_time")
    @classmethod
    def validate_time(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("scheduled_time is required")
        # Accept HH:MM or HH:MM:SS
        v = v.strip()
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                datetime.strptime(v, fmt)
                # normalize to HH:MM
                dt = datetime.strptime(v, fmt)
                return dt.strftime("%H:%M")
            except ValueError:
                continue
        raise ValueError("scheduled_time must be HH:MM")

    @field_validator("duration_minutes")
    @classmethod
    def validate_duration(cls, v: int) -> int:
        if v is None:
            raise ValueError("duration_minutes is required")
        if not isinstance(v, int):
            raise ValueError("duration_minutes must be integer")
        if v < 5 or v > 120:
            raise ValueError("duration_minutes must be between 5 and 120")
        return v

class InterviewResponse(BaseModel):
    interview_id: str
    candidate_name: str
    candidate_email: Optional[str] = None
    job_title: str
    job_description: str
    resume_text: str
    scheduled_date: str
    scheduled_time: str
    duration_minutes: int
    status: StatusType
    created_at: str

class InterviewSummary(BaseModel):
    interview_id: str
    candidate_name: str
    candidate_email: Optional[str] = None
    job_title: str
    scheduled_date: str
    scheduled_time: str
    duration_minutes: int
    status: StatusType
    created_at: str

class InterviewCreateResponse(BaseModel):
    interview_id: str
    status: StatusType
    scheduled_date: str
    scheduled_time: str
    duration_minutes: int
    candidate_name: str
    job_title: str

class InterviewWindowInfo(BaseModel):
    can_join: bool
    window_start: str
    window_end: str
    message: str
    status: str  # not_started | joinable | ended | cancelled | completed
