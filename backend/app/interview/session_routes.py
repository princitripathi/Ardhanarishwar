import os
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.interview.service import get_interview, get_window_info
import app.interview.session_service as sess_svc
from app.interview.engine import generate_interview_plan, generate_next_question, generate_final_report
from app.interview.evaluator import evaluate_answer


def _is_session_time_expired(sess: dict, interview: dict) -> bool:
    try:
        started = sess.get("started_at")
        if not started:
            return False
        from datetime import timezone
        started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
        if started_dt.tzinfo is None:
            started_dt = started_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        duration = interview.get("duration_minutes", 30) if interview else 30
        elapsed = (now - started_dt).total_seconds()
        return elapsed > duration * 60
    except Exception:
        return False


def _enrich_final_report(report: dict, sess: dict, interview: dict, reason: str) -> dict:
    try:
        questions = sess.get("questions_asked") or []
        answers = sess.get("answers") or []
        evaluations = sess.get("evaluations") or []
        total = sess.get("total_questions", interview.get("duration_minutes") if interview else 10) if isinstance(sess.get("total_questions"), int) else sess.get("total_questions", 10)
        # Ensure total is int
        try:
            total = int(total)
        except:
            total = 10
        answered = len(answers)
        # If report already has answers but sess not yet updated, use answers len
        # Ensure report contains actual counts
        report.setdefault("answered_count", answered)
        report.setdefault("total_questions", total)
        report.setdefault("completion_reason", reason)
        # Human-readable answered statement
        report["questions_answered"] = f"{answered} of {total} questions answered."
        # Ensure topics_covered reflects actual
        if not report.get("topics_covered"):
            report["topics_covered"] = list({q.get("topic") for q in questions if q.get("topic")})
        # Ensure scores are from actual evaluations, not generic fallback
        # If overall_score is generic 5 and we have evaluations, recalc
        if evaluations and report.get("overall_score") == 5 and any(e.get("score", 5) != 5 for e in evaluations):
            avg = sum(e.get("score", 5) for e in evaluations) / len(evaluations) if evaluations else 5
            report["overall_score"] = int(round(avg))
        return report
    except Exception:
        return report

router = APIRouter(prefix="/api/interviews", tags=["interview-sessions"])

# --- Request/Response models ---

class SessionStartRequest(BaseModel):
    total_questions: Optional[int] = 10

class SessionAnswerRequest(BaseModel):
    session_id: str
    answer: str

class SessionEvaluationPublic(BaseModel):
    score: int
    feedback: str

# Helpers

def _is_development_mode() -> bool:
    """Return True if running in development/local/testing mode where 3-question Quick Test is allowed."""
    for key in ("APP_ENV", "ENV", "ENVIRONMENT"):
        val = (os.getenv(key) or "").strip().lower()
        if val:
            return val in ("development", "dev", "local", "test", "testing", "develop")
    # Fallback: if pytest is running, treat as dev for testing convenience
    if os.getenv("PYTEST_CURRENT_TEST"):
        return True
    # Default to dev when APP_ENV is unset locally, but treat missing as not dev for security
    # We check for common dev indicator: if not in production, allow only if APP_ENV explicitly dev
    # So missing env => production (secure default)
    return False


def _validate_total_questions(n: Optional[int]) -> int:
    if n is None:
        return 10
    try:
        ni = int(n)
    except Exception:
        raise HTTPException(status_code=422, detail="total_questions must be integer 5-30")
    # Allow 3 only in development/testing mode (Quick Test)
    if ni == 3:
        if _is_development_mode():
            return ni
        raise HTTPException(status_code=422, detail="total_questions must be between 5 and 30 (3 allowed only in development mode)")
    if ni < 5 or ni > 30:
        if _is_development_mode() and ni == 3:
            return ni
        raise HTTPException(status_code=422, detail="total_questions must be between 5 and 30")
    return ni


def _safe_session_response(sess: dict, include_question: bool = True):
    """Return safe candidate-facing data."""
    questions = sess.get("questions_asked") or []
    current_q = questions[-1] if questions else None
    total = sess.get("total_questions", 10)
    qnum = sess.get("question_number", 1)
    # Don't expose evaluation details, plan internals fully? Plan topics are ok to hide? Spec says don't expose internal prompts/reasoning.
    # We'll expose minimal.
    resp = {
        "session_id": sess["session_id"],
        "interview_id": sess["interview_id"],
        "status": sess["status"],
        "question_number": qnum,
        "total_questions": total,
        "started_at": sess.get("started_at"),
        "completed_at": sess.get("completed_at"),
    }
    if include_question and current_q and sess["status"] == "active":
        resp.update({
            "question": current_q.get("question"),
            "topic": current_q.get("topic"),
            "difficulty": current_q.get("difficulty"),
            "is_follow_up": current_q.get("is_follow_up", False),
        })
    elif sess["status"] == "completed":
        # include final report summary
        resp["final_report"] = sess.get("final_report")
    return resp


@router.post("/{interview_id}/session/start")
async def start_session(interview_id: str, payload: Optional[SessionStartRequest] = None):
    if payload is None:
        payload = SessionStartRequest()
    total_questions = _validate_total_questions(payload.total_questions)

    interview = get_interview(interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    # Check window & interview status - reuse existing logic
    # If interview is cancelled/completed, fail
    if interview["status"] == "cancelled":
        raise HTTPException(status_code=400, detail="Interview has been cancelled")
    if interview["status"] == "completed":
        raise HTTPException(status_code=400, detail="Interview has been completed")

    # Check window
    window = get_window_info(interview)
    # Allow if already active or joinable; if not_started/ended => block
    # But also handle case where interview still scheduled but window joinable
    if window and not window.get("can_join") and interview["status"] != "active":
        # if status is scheduled and window not joinable -> cannot start
        # Provide specific messages for before/after window
        status = window.get("status")
        if status == "not_started":
            raise HTTPException(status_code=400, detail="Interview has not started yet. Available 5 minutes before scheduled time.")
        elif status == "ended":
            raise HTTPException(status_code=400, detail="Interview window has ended")
        else:
            raise HTTPException(status_code=400, detail=window.get("message", "Cannot start interview"))

    # Prevent multiple active sessions?
    existing = sess_svc.get_session_by_interview(interview_id)
    if existing and existing["status"] == "active":
        # return existing instead of creating new? Spec says should not allow duplicate? We'll return existing
        raise HTTPException(status_code=400, detail="Interview session already active")

    # If existing completed, cannot restart?
    if existing and existing["status"] == "completed":
        raise HTTPException(status_code=400, detail="Interview session already completed")

    # Generate plan and first question
    try:
        plan = await generate_interview_plan(
            job_description=interview["job_description"],
            resume_text=interview["resume_text"],
            job_title=interview["job_title"],
        )
        first_q = await generate_next_question(
            interview_plan=plan,
            job_description=interview["job_description"],
            resume_text=interview["resume_text"],
            questions_asked=[],
            answers=[],
            evaluations=[],
            question_number=1,
            total_questions=total_questions,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate interview: {str(e)}")

    sess = sess_svc.create_session(interview_id, plan, first_q, total_questions)

    # Mark interview as active if still scheduled
    if interview["status"] == "scheduled":
        from app.interview.service import update_status
        update_status(interview_id, "active")

    return {
        "session_id": sess["session_id"],
        "status": sess["status"],
        "question_number": sess["question_number"],
        "question": first_q["question"],
        "topic": first_q["topic"],
        "difficulty": first_q.get("difficulty", "medium"),
        "total_questions": total_questions,
        "interview_plan": [t["name"] for t in plan.get("topics", [])],  # expose topic names only
    }


@router.get("/{interview_id}/session")
async def get_session_info(interview_id: str):
    interview = get_interview(interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    sess = sess_svc.get_session_by_interview(interview_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    # Provide safe view
    questions = sess.get("questions_asked") or []
    answers = sess.get("answers") or []
    evaluations = sess.get("evaluations") or []
    # Expose progress but not private eval details
    current_q = questions[-1] if questions else None
    resp = {
        "session_id": sess["session_id"],
        "interview_id": sess["interview_id"],
        "status": sess["status"],
        "question_number": sess["question_number"],
        "total_questions": sess["total_questions"],
        "current_topic": sess.get("current_topic"),
        "started_at": sess.get("started_at"),
        "completed_at": sess.get("completed_at"),
        "questions_asked": len(questions),
        "answers_given": len(answers),
        "interview_plan": sess.get("interview_plan"),
    }
    if current_q and sess["status"] == "active":
        resp["current_question"] = current_q.get("question")
        resp["topic"] = current_q.get("topic")
        resp["difficulty"] = current_q.get("difficulty")
    if sess["status"] == "completed":
        resp["final_report"] = sess.get("final_report")
        resp["evaluations_count"] = len(evaluations)
    return resp


@router.post("/{interview_id}/session/answer")
async def submit_answer(interview_id: str, payload: SessionAnswerRequest):
    if not payload.session_id or not payload.session_id.strip():
        raise HTTPException(status_code=422, detail="session_id is required")
    if payload.answer is None or not payload.answer.strip():
        raise HTTPException(status_code=422, detail="Answer cannot be empty")
    answer_text = payload.answer.strip()
    # Could also allow answer via STT later, keep as text only for now

    interview = get_interview(interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    sess = sess_svc.get_session(payload.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess["interview_id"] != interview_id:
        raise HTTPException(status_code=400, detail="Session does not belong to this interview")
    if sess["status"] != "active":
        raise HTTPException(status_code=400, detail=f"Session is {sess['status']}, cannot accept answer")

    # Backend timer validation - do not allow bypass via browser
    if _is_session_time_expired(sess, interview):
        # Auto-complete with time_expired reason
        questions_exp = sess.get("questions_asked") or []
        answers_exp = sess.get("answers") or []
        evals_exp = sess.get("evaluations") or []
        try:
            report_exp = await generate_final_report(
                interview_plan=sess.get("interview_plan"),
                questions_asked=questions_exp,
                answers=answers_exp,
                evaluations=evals_exp,
            )
        except Exception:
            report_exp = {
                "overall_score": 5,
                "technical_score": 5,
                "communication_score": 5,
                "problem_solving_score": 5,
                "strengths": ["Participated in interview"],
                "weaknesses": ["Time expired - limited data"],
                "topics_covered": list({q.get("topic") for q in questions_exp}),
                "recommendation": "Moderate",
                "summary": "Interview time expired.",
                "detailed_feedback": "Interview ended due to time limit.",
            }
        report_exp = _enrich_final_report(report_exp, sess, interview, "time_expired")
        sess_svc.complete_session(sess["session_id"], report_exp)
        raise HTTPException(status_code=400, detail="Interview time has expired. Session completed.")

    # Validate question_number not exceeded
    total = sess["total_questions"]
    current_q_num = sess["question_number"]
    questions = sess.get("questions_asked") or []
    if not questions:
        raise HTTPException(status_code=500, detail="Corrupted session: no questions")
    current_q = questions[-1]

    # Evaluate answer
    try:
        evaluation = await evaluate_answer(
            question=current_q,
            answer=answer_text,
            resume_text=interview["resume_text"],
            job_description=interview["job_description"],
            topic=current_q.get("topic", ""),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")

    # Check if this was the last question
    answers = sess.get("answers") or []
    evaluations = sess.get("evaluations") or []
    is_last = len(answers) + 1 >= total  # answers before adding +1

    if is_last:
        # Append without next question, then generate final report and complete
        # First persist answer+eval
        # We need to append evaluation and mark question count final?
        # Use helper that appends without next question then complete
        updated = sess_svc.append_answer_and_evaluation(payload.session_id, answer_text, evaluation, next_question=None)
        # Generate final report
        # Reload to get updated lists including just added
        sess_latest = sess_svc.get_session(payload.session_id)
        questions_latest = sess_latest.get("questions_asked") or []
        answers_latest = sess_latest.get("answers") or []
        evals_latest = sess_latest.get("evaluations") or []
        try:
            report = await generate_final_report(
                interview_plan=sess_latest.get("interview_plan"),
                questions_asked=questions_latest,
                answers=answers_latest,
                evaluations=evals_latest,
            )
        except Exception as e:
            report = {
                "overall_score": evaluation.get("score", 5),
                "technical_score": evaluation.get("correctness", 5),
                "communication_score": evaluation.get("clarity", 5),
                "problem_solving_score": evaluation.get("depth", 5),
                "strengths": evaluation.get("strengths", []),
                "weaknesses": evaluation.get("weaknesses", []),
                "topics_covered": list({q.get("topic") for q in questions_latest}),
                "recommendation": "Moderate",
                "summary": "Interview completed.",
                "detailed_feedback": "Fallback final report.",
            }
        report = _enrich_final_report(report, sess_latest, interview, "questions_completed")
        completed = sess_svc.complete_session(payload.session_id, report)
        return {
            "question_number": current_q_num,
            "status": "completed",
            "message": "Interview completed",
            "final_report": report,
            "evaluation": {
                "score": evaluation["score"],
                "feedback": evaluation["feedback"],
            },
        }
    else:
        # Not last: generate next question adaptively
        # Build next question number
        next_q_num = current_q_num + 1
        # Need updated evaluations list to include current eval for adaptive hint
        # Use existing evaluations + new one for generation
        interim_evals = (evaluations or []) + [evaluation]
        interim_answers_raw = (answers or []) + [{"answer": answer_text, "question_number": current_q_num}]
        # Convert to expected format for engine: list of dicts
        # answers param expects list of dicts with 'answer'
        # questions_asked currently is list of question dicts
        try:
            next_q = await generate_next_question(
                interview_plan=sess.get("interview_plan"),
                job_description=interview["job_description"],
                resume_text=interview["resume_text"],
                questions_asked=questions,
                answers=interim_answers_raw,
                evaluations=interim_evals,
                question_number=next_q_num,
                total_questions=total,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to generate next question: {str(e)}")

        # Persist
        updated = sess_svc.append_answer_and_evaluation(payload.session_id, answer_text, evaluation, next_question=next_q)

        return {
            "question_number": next_q["question_number"],
            "question": next_q["question"],
            "topic": next_q["topic"],
            "difficulty": next_q.get("difficulty", "medium"),
            "status": "active",
            "total_questions": total,
            "is_follow_up": next_q.get("is_follow_up", False),
            # expose safe evaluation feedback optionally? Spec says don't expose internal details, so minimal
        }


@router.post("/{interview_id}/session/end")
async def end_session(interview_id: str, payload: Optional[dict] = None):
    # payload may contain session_id; if not, use latest by interview
    session_id = None
    if payload and isinstance(payload, dict):
        session_id = payload.get("session_id")
    interview = get_interview(interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    sess = None
    if session_id:
        sess = sess_svc.get_session(session_id)
        if not sess:
            raise HTTPException(status_code=404, detail="Session not found")
        if sess["interview_id"] != interview_id:
            raise HTTPException(status_code=400, detail="Session does not belong to this interview")
    else:
        sess = sess_svc.get_session_by_interview(interview_id)
        if not sess:
            raise HTTPException(status_code=404, detail="Session not found")
    if sess["status"] == "completed":
        raise HTTPException(status_code=400, detail="Session already completed")
    if sess["status"] != "active":
        raise HTTPException(status_code=400, detail=f"Session is {sess['status']}, cannot end")

    # Generate final report with whatever answers we have
    questions = sess.get("questions_asked") or []
    answers = sess.get("answers") or []
    evaluations = sess.get("evaluations") or []
    # Determine completion reason
    reason = "time_expired" if _is_session_time_expired(sess, interview) else "early_end"
    # Also if all questions answered, treat as questions_completed (fallback for manual end after all)
    if len(answers) >= sess.get("total_questions", 10):
        reason = "questions_completed"
    try:
        report = await generate_final_report(
            interview_plan=sess.get("interview_plan"),
            questions_asked=questions,
            answers=answers,
            evaluations=evaluations,
        )
    except Exception:
        report = {
            "overall_score": 5,
            "technical_score": 5,
            "communication_score": 5,
            "problem_solving_score": 5,
            "strengths": ["Participated in interview"],
            "weaknesses": ["Early termination - limited data"] if reason == "early_end" else ["Time expired - limited data"],
            "topics_covered": list({q.get("topic") for q in questions}),
            "recommendation": "Moderate",
            "summary": "Interview ended early." if reason == "early_end" else "Interview time expired.",
            "detailed_feedback": "Interview was ended before completing all questions." if reason == "early_end" else "Interview ended due to time limit.",
        }
    report = _enrich_final_report(report, sess, interview, reason)
    completed = sess_svc.complete_session(sess["session_id"], report)
    return {
        "session_id": completed["session_id"],
        "status": "completed",
        "final_report": report,
        "message": "Interview session ended",
    }
