from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional, List

from app.services import user_memory as mem
from app.services.security import is_valid_id, sanitize_for_log

router = APIRouter(prefix="/api/memory", tags=["memory"])

class MemoryUpdate(BaseModel):
    user_id: Optional[str] = None
    preferred_name: Optional[str] = None
    career_goal: Optional[str] = None
    target_role: Optional[str] = None
    known_skills: Optional[List[str]] = None
    learning_interests: Optional[List[str]] = None
    professional_preferences: Optional[str] = None

    @field_validator("user_id")
    @classmethod
    def check_uid(cls, v):
        if v is None:
            return v
        if not is_valid_id(v.strip(), 64):
            raise ValueError("invalid user_id")
        return v.strip()
    @field_validator("preferred_name", "career_goal", "target_role", "professional_preferences")
    @classmethod
    def check_len(cls, v):
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("must be string")
        if len(v) > 200:
            raise ValueError("field too long (max 200)")
        return v

class MemoryClear(BaseModel):
    user_id: Optional[str] = None
    @field_validator("user_id")
    @classmethod
    def check_uid(cls, v):
        if v is None:
            return v
        if not is_valid_id(v.strip(), 64):
            raise ValueError("invalid user_id")
        return v.strip()

def _validate_user_id_or_400(uid: str):
    if not is_valid_id(uid, 64):
        raise HTTPException(status_code=400, detail="Invalid user_id")
    if ".." in uid or "/" in uid or "\\" in uid:
        raise HTTPException(status_code=400, detail="Invalid user_id")

@router.get("/{user_id}")
async def get_memory(user_id: str):
    _validate_user_id_or_400(user_id)
    profile = mem.get_profile(user_id)
    if not profile:
        return {"user_id": user_id, "profile": None, "exists": False}
    return {"user_id": user_id, "profile": profile, "exists": True}

@router.get("/")
async def get_memory_query(user_id: str = Query(default=mem.DEFAULT_USER_ID)):
    _validate_user_id_or_400(user_id)
    profile = mem.get_profile(user_id)
    if not profile:
        return {"user_id": user_id, "profile": None, "exists": False}
    return {"user_id": user_id, "profile": profile, "exists": True}

@router.post("/")
async def upsert_memory(update: MemoryUpdate):
    uid = update.user_id or mem.DEFAULT_USER_ID
    data = {k: v for k, v in update.model_dump().items() if k != "user_id" and v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    # Filter sensitive and bound via upsert
    profile = mem.upsert_profile(uid, data)
    return {"user_id": uid, "profile": profile}

@router.put("/{user_id}")
async def put_memory(user_id: str, update: MemoryUpdate):
    _validate_user_id_or_400(user_id)
    data = {k: v for k, v in update.model_dump().items() if k != "user_id" and v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    profile = mem.upsert_profile(user_id, data)
    return {"user_id": user_id, "profile": profile}

@router.delete("/{user_id}")
async def delete_memory(user_id: str):
    _validate_user_id_or_400(user_id)
    ok = mem.delete_profile(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"status": "deleted", "user_id": user_id}

@router.post("/clear")
async def clear_memory(body: MemoryClear = None):
    if body and body.user_id:
        _validate_user_id_or_400(body.user_id)
        ok = mem.delete_profile(body.user_id)
        return {"status": "cleared" if ok else "not_found", "user_id": body.user_id}
    mem.clear_all()
    return {"status": "cleared_all"}

@router.get("/context/{user_id}")
async def get_context(user_id: str):
    _validate_user_id_or_400(user_id)
    ctx = mem.build_memory_context(user_id)
    return {"user_id": user_id, "context": ctx, "has_context": bool(ctx)}
