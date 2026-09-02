from fastapi import APIRouter, HTTPException
from typing import List
from app.interview.models import InterviewCreateRequest, InterviewCreateResponse, InterviewResponse, InterviewSummary
from app.interview import service

router = APIRouter(prefix="/api/interviews", tags=["interviews"])

@router.post("", response_model=InterviewCreateResponse, status_code=201)
async def create_interview(payload: InterviewCreateRequest):
    try:
        data = payload.model_dump()
        interview = service.create_interview(data)
        return InterviewCreateResponse(
            interview_id=interview["interview_id"],
            status=interview["status"],
            scheduled_date=interview["scheduled_date"],
            scheduled_time=interview["scheduled_time"],
            duration_minutes=interview["duration_minutes"],
            candidate_name=interview["candidate_name"],
            job_title=interview["job_title"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=List[InterviewSummary])
async def list_interviews():
    interviews = service.list_interviews()
    return [
        InterviewSummary(
            interview_id=i["interview_id"],
            candidate_name=i["candidate_name"],
            candidate_email=i.get("candidate_email"),
            job_title=i["job_title"],
            scheduled_date=i["scheduled_date"],
            scheduled_time=i["scheduled_time"],
            duration_minutes=i["duration_minutes"],
            status=i["status"],
            created_at=i["created_at"],
        )
        for i in interviews
    ]

@router.get("/{interview_id}")
async def get_interview(interview_id: str):
    interview = service.get_interview(interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    window = service.get_window_info(interview)
    # Return interview info without exposing unnecessary internal? Keep resume/job desc but not too large?
    # For lobby we need candidate, job, scheduled, duration, status, window
    return {
        "interview_id": interview["interview_id"],
        "candidate_name": interview["candidate_name"],
        "candidate_email": interview.get("candidate_email"),
        "job_title": interview["job_title"],
        "job_description": interview["job_description"],
        "resume_text": interview["resume_text"],
        "scheduled_date": interview["scheduled_date"],
        "scheduled_time": interview["scheduled_time"],
        "duration_minutes": interview["duration_minutes"],
        "status": interview["status"],
        "created_at": interview["created_at"],
        "window": window,
    }

@router.post("/{interview_id}/start")
async def start_interview(interview_id: str):
    interview = service.get_interview(interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    can, msg = service.can_start(interview)
    if not can:
        raise HTTPException(status_code=400, detail=msg)
    updated = service.update_status(interview_id, "active")
    window = service.get_window_info(updated)
    return {
        "interview_id": updated["interview_id"],
        "status": updated["status"],
        "message": "Interview session started.",
        "window": window,
    }

@router.post("/{interview_id}/cancel")
async def cancel_interview(interview_id: str):
    interview = service.get_interview(interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    if interview["status"] == "cancelled":
        raise HTTPException(status_code=400, detail="Interview is already cancelled")
    if interview["status"] == "completed":
        raise HTTPException(status_code=400, detail="Interview has been completed")
    updated = service.update_status(interview_id, "cancelled")
    return {
        "interview_id": updated["interview_id"],
        "status": updated["status"],
        "message": "Interview cancelled",
    }
