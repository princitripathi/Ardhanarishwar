import logging
import json
from typing import Dict, List, Optional

from app.services.llm import generate_response, OllamaError
from app.interview.prompts import PLAN_SYSTEM_PROMPT, QUESTION_SYSTEM_PROMPT, FINAL_REPORT_SYSTEM_PROMPT
from app.interview.llm_helpers import extract_json, normalize_question, normalize_plan, normalize_final_report

logger = logging.getLogger(__name__)

# Phase 7: lightweight validation for structured interview outputs
try:
    from app.services.validation import validate_plan, validate_question, validate_final_report
    _VALIDATION_AVAILABLE = True
except Exception as _e:
    logger.warning(f"Interview validation not available: {_e}")
    _VALIDATION_AVAILABLE = False
    validate_plan = lambda *a, **k: (True, [], None)
    validate_question = lambda *a, **k: (True, [], None)
    validate_final_report = lambda *a, **k: (True, [], None)


async def generate_interview_plan(job_description: str, resume_text: str, job_title: str = "") -> Dict:
    prompt = f"""Job Title: {job_title}

Job Description:
{job_description[:3000]}

Candidate Resume:
{resume_text[:3000]}

Generate interview plan JSON as described.
"""
    try:
        resp = await generate_response(prompt, system_prompt=PLAN_SYSTEM_PROMPT)
        raw = extract_json(resp.response)
        if raw is None:
            logger.warning(f"Plan JSON parse failed: {resp.response[:600]}")
            # fallback heuristic
            return _heuristic_plan(job_description, resume_text, job_title)
        normalized = normalize_plan(raw, job_title)
        # Phase 7: validate required fields
        if _VALIDATION_AVAILABLE:
            is_valid, issues, _ = validate_plan(normalized, job_title)
            if not is_valid:
                logger.warning(f"Plan validation failed: {issues}, using heuristic fallback")
                return _heuristic_plan(job_description, resume_text, job_title)
        return normalized
    except OllamaError as e:
        logger.error(f"Plan OllamaError: {e.message}")
        return _heuristic_plan(job_description, resume_text, job_title)
    except Exception:
        logger.exception("Plan generation failed")
        return _heuristic_plan(job_description, resume_text, job_title)


def _heuristic_plan(job_description: str, resume_text: str, job_title: str) -> Dict:
    jd_lower = (job_description or "").lower()
    resume_lower = (resume_text or "").lower()
    title_lower = (job_title or "").lower()
    # Determine role family
    topics = [
        {"name": "Introduction", "focus": "Candidate background and motivation for the role"},
        {"name": "Resume & Projects", "focus": "Deep dive into resume projects and experience"},
    ]
    # map keywords to topics
    if any(k in jd_lower or k in title_lower for k in ["data analyst", "analytics", "sql", "tableau", "power bi", "excel"]):
        topics += [
            {"name": "SQL & Data Handling", "focus": "SQL queries and data manipulation"},
            {"name": "Data Analysis", "focus": "Analytical thinking and metrics"},
            {"name": "Visualization", "focus": "Data storytelling and visualization tools"},
            {"name": "Statistics", "focus": "Statistical concepts and experimentation"},
        ]
    elif any(k in jd_lower or k in title_lower for k in ["backend", "api", "microservice", "java", "node", "database"]):
        topics += [
            {"name": "Backend Fundamentals", "focus": "API design and server architecture"},
            {"name": "Databases", "focus": "Relational/NoSQL design and queries"},
            {"name": "System Design", "focus": "Scalability and architecture trade-offs"},
            {"name": "Coding & Algorithms", "focus": "Problem solving and code quality"},
        ]
    elif any(k in jd_lower or k in title_lower for k in ["hr", "human resource", "recruiter", "talent"]):
        topics += [
            {"name": "HR Fundamentals", "focus": "HR policies and employee lifecycle"},
            {"name": "Communication", "focus": "Stakeholder management and communication"},
            {"name": "Labor Laws", "focus": "Compliance and regulatory knowledge"},
            {"name": "Conflict Resolution", "focus": "Handling workplace challenges"},
        ]
    elif any(k in jd_lower or k in title_lower for k in ["frontend", "react", "angular", "vue", "ui", "ux"]):
        topics += [
            {"name": "Frontend Core", "focus": "HTML/CSS/JS fundamentals"},
            {"name": "Framework Knowledge", "focus": "Component design and state management"},
            {"name": "Performance", "focus": "Optimization and accessibility"},
            {"name": "Design Collaboration", "focus": "Working with designers and UX"},
        ]
    elif any(k in jd_lower or k in title_lower for k in ["ai", "ml", "machine learning", "llm", "generative", "data science"]):
        topics += [
            {"name": "Python", "focus": "Python for ML and data tasks"},
            {"name": "Machine Learning", "focus": "Algorithms and model evaluation"},
            {"name": "Generative AI / LLM", "focus": "LLM concepts, RAG, embeddings"},
            {"name": "MLOps & Deployment", "focus": "Model deployment and monitoring"},
        ]
    else:
        # generic extraction: try to pick top nouns from JD?
        topics += [
            {"name": "Role Fundamentals", "focus": f"Core knowledge for {job_title or 'the role'}"},
            {"name": "Technical Skills", "focus": "Required technical abilities from JD"},
            {"name": "Domain Knowledge", "focus": "Role-specific expertise"},
            {"name": "Problem Solving", "focus": "Practical problem scenarios"},
        ]
    # always add behavioral and closing
    topics += [
        {"name": "Problem Solving", "focus": "Approach to real work challenges"} if not any(t["name"] == "Problem Solving" for t in topics) else None,
        {"name": "Behavioral & Communication", "focus": "Teamwork, leadership, communication"},
        {"name": "Candidate Questions", "focus": "Candidate's questions and closing"},
    ]
    topics = [t for t in topics if t is not None]
    # deduplicate
    seen = set()
    uniq = []
    for t in topics:
        if t["name"].lower() not in seen:
            seen.add(t["name"].lower())
            uniq.append(t)
    # cap 10
    return {"topics": uniq[:10]}


async def generate_next_question(
    interview_plan: Dict,
    job_description: str,
    resume_text: str,
    questions_asked: List[Dict],
    answers: List[Dict],
    evaluations: List[Dict],
    question_number: int,
    total_questions: int,
) -> Dict:
    """Generate next adaptive question."""
    topics = interview_plan.get("topics", [])
    topic_names = [t["name"] for t in topics]

    # Determine current topic adaptively
    # Simple logic: rotate through plan, but allow follow-up staying on same topic
    last_eval = evaluations[-1] if evaluations else None
    last_q = questions_asked[-1] if questions_asked else None

    # If last evaluation says follow_up_needed and we are not at end, stay on same topic
    follow_up = False
    next_topic = None
    if last_eval and last_eval.get("follow_up_needed") and len(questions_asked) < total_questions:
        # 50% chance to actually do follow-up, otherwise move on - but we will honor follow_up_needed
        # If difficulty adjustment suggests increase, we stay but harder
        follow_up = True
        next_topic = last_q.get("topic") if last_q else topic_names[min(question_number-1, len(topic_names)-1)]
    else:
        # move to next plan topic
        # Use question_number to index into topics (question_number is 1-indexed for next question)
        idx = min(question_number - 1, len(topic_names) - 1)
        # but skip introduction after first question
        if question_number > 1 and idx == 0:
            idx = min(1, len(topic_names)-1)
        # progress through topics proportionally
        # e.g., total 10, topics 7 -> map linearly
        if len(topic_names) > 0:
            # proportional mapping
            prog = (question_number - 1) / max(1, total_questions - 1)
            idx = int(prog * (len(topic_names) - 1))
            # ensure not repeating last topic too quickly unless follow-up
            if last_q and topic_names[idx] == last_q.get("topic") and idx < len(topic_names) - 1 and not follow_up:
                idx = min(idx + 1, len(topic_names) - 1)
        next_topic = topic_names[idx] if topic_names else "General"

    difficulty_hint = "medium"
    if last_eval:
        adj = last_eval.get("difficulty_adjustment", "maintain")
        if adj == "increase":
            difficulty_hint = "hard"
        elif adj == "decrease":
            difficulty_hint = "easy"

    # Build prompt context
    history_snippet = ""
    for i, q in enumerate(questions_asked[-3:]):  # last 3
        history_snippet += f"Q{i+1} ({q.get('topic')}): {q.get('question')}\n"
        if i < len(answers):
            ans = answers[i].get("answer", "") if isinstance(answers[i], dict) else str(answers[i])
            history_snippet += f"A{i+1}: {ans[:300]}\n"
            if i < len(evaluations):
                ev = evaluations[i]
                history_snippet += f"Eval: score {ev.get('score')} follow_up_needed={ev.get('follow_up_needed')}\n"

    prompt = f"""Interview Plan Topics: {', '.join(topic_names)}

Job Title context: use JD and resume to ground question.

Job Description (excerpt):
{job_description[:1500]}

Resume (excerpt):
{resume_text[:1500]}

History (last few turns):
{history_snippet or 'No history - this is the first substantive question.'}

Generate next question:
- question_number: {question_number}
- total_questions: {total_questions}
- target topic: {next_topic}
- difficulty hint: {difficulty_hint} (adapt: increase if previous strong, decrease if weak)
- is_follow_up: {str(follow_up).lower()} (true if probing deeper due to incomplete/vague previous answer)

Return JSON only.
"""
    try:
        resp = await generate_response(prompt, system_prompt=QUESTION_SYSTEM_PROMPT)
        raw = extract_json(resp.response)
        if raw is None:
            logger.warning(f"Question JSON parse failed: {resp.response[:600]}")
            return _fallback_question(question_number, next_topic, difficulty_hint, follow_up, resume_text, job_description)
        q = normalize_question(raw, question_number, fallback_topic=next_topic)
        # ensure follow_up consistency
        if follow_up and not q.get("is_follow_up"):
            # if we expected follow-up, keep topic same but respect model
            q["topic"] = next_topic
        # Phase 7: validate required fields
        if _VALIDATION_AVAILABLE:
            is_valid, issues, _ = validate_question(q, question_number)
            if not is_valid:
                logger.warning(f"Question validation failed: {issues}, using fallback")
                return _fallback_question(question_number, next_topic, difficulty_hint, follow_up, resume_text, job_description)
        return q
    except OllamaError as e:
        logger.error(f"Question OllamaError: {e.message}")
        return _fallback_question(question_number, next_topic, difficulty_hint, follow_up, resume_text, job_description)
    except Exception:
        logger.exception("Question generation failed")
        return _fallback_question(question_number, next_topic, difficulty_hint, follow_up, resume_text, job_description)


def _fallback_question(question_number: int, topic: str, difficulty: str, is_follow: bool, resume_text: str, job_description: str) -> Dict:
    # Try to reference resume snippet
    resume_snippet = ""
    if resume_text and len(resume_text) > 20:
        # take first project line
        lines = [l.strip() for l in resume_text.split("\n") if l.strip()][:3]
        if lines:
            resume_snippet = lines[0][:80]
    if is_follow:
        text = f"You mentioned something related to {topic} in your previous answer. Could you elaborate further and provide a concrete example?"
    elif topic.lower() == "introduction":
        text = "Could you briefly introduce yourself and highlight how your background aligns with this role?"
    elif "resume" in topic.lower() or "project" in topic.lower():
        if resume_snippet:
            text = f'You mentioned "{resume_snippet}" in your resume. Could you walk me through that experience and your specific contributions?'
        else:
            text = "Could you describe a project from your resume that is most relevant to this role and your key contributions?"
    else:
        text = f"Regarding {topic}, could you explain a key concept or approach you would use in this role, with an example from your experience?"
    return {
        "question": text,
        "topic": topic,
        "difficulty": difficulty if difficulty in ("easy", "medium", "hard") else "medium",
        "question_number": question_number,
        "expected_focus": f"Clear explanation relevant to {topic}",
        "is_follow_up": is_follow,
    }


async def generate_final_report(
    interview_plan: Dict,
    questions_asked: List[Dict],
    answers: List[Dict],
    evaluations: List[Dict],
) -> Dict:
    topics_covered = list({q.get("topic", "General") for q in questions_asked})
    avg = sum(e.get("score", 5) for e in evaluations) / len(evaluations) if evaluations else 5
    prompt = f"""Interview Plan: {json.dumps(interview_plan)}

Questions & Answers:
"""
    for i, q in enumerate(questions_asked):
        prompt += f"\nQ{i+1} [{q.get('topic')}]: {q.get('question')}\n"
        if i < len(answers):
            ans = answers[i].get("answer", "") if isinstance(answers[i], dict) else str(answers[i])
            prompt += f"A{i+1}: {ans[:500]}\n"
        if i < len(evaluations):
            ev = evaluations[i]
            prompt += f"Eval: score={ev.get('score')} correctness={ev.get('correctness')} relevance={ev.get('relevance')} depth={ev.get('depth')} clarity={ev.get('clarity')} strengths={ev.get('strengths')} weaknesses={ev.get('weaknesses')}\n"
    prompt += f"\nAverage score: {avg:.1f}\nTopics covered: {', '.join(topics_covered)}\nGenerate final report JSON."

    try:
        resp = await generate_response(prompt, system_prompt=FINAL_REPORT_SYSTEM_PROMPT)
        raw = extract_json(resp.response)
        if raw is None:
            logger.warning(f"Final report JSON parse failed: {resp.response[:600]}")
            return _heuristic_report(evaluations, topics_covered)
        normalized = normalize_final_report(raw, topics_covered)
        if _VALIDATION_AVAILABLE:
            is_valid, issues, _ = validate_final_report(normalized, topics_covered)
            if not is_valid:
                logger.warning(f"Final report validation failed: {issues}, using heuristic")
                return _heuristic_report(evaluations, topics_covered)
        return normalized
    except OllamaError:
        logger.error("Final report Ollama unavailable")
        return _heuristic_report(evaluations, topics_covered)
    except Exception:
        logger.exception("Final report failed")
        return _heuristic_report(evaluations, topics_covered)


def _heuristic_report(evaluations: List[Dict], topics_covered: List[str]) -> Dict:
    if not evaluations:
        avg = 5
        tech = 5
        comm = 5
        prob = 5
        return {
            "overall_score": 5,
            "technical_score": 5,
            "communication_score": 5,
            "problem_solving_score": 5,
            "strengths": ["Engaged in interview process"],
            "weaknesses": ["No substantive answers provided for evaluation."],
            "topics_covered": topics_covered,
            "recommendation": "Needs Improvement",
            "summary": "No substantive answers were provided during the interview. Recommendation: Needs Improvement.",
            "detailed_feedback": "The interview was completed without sufficient responses to assess technical and communication skills.",
        }
    avg = sum(e.get("score", 5) for e in evaluations) / len(evaluations)
    tech = sum(e.get("correctness", 5) for e in evaluations) / len(evaluations)
    comm = sum(e.get("clarity", 5) for e in evaluations) / len(evaluations)
    prob = sum(e.get("depth", 5) for e in evaluations) / len(evaluations)
    relevance_avg = sum(e.get("relevance", 5) for e in evaluations) / len(evaluations)
    if avg >= 8:
        rec = "Strong"
    elif avg >= 5:
        rec = "Moderate"
    else:
        rec = "Needs Improvement"
    # Aggregate strengths/weaknesses intelligently from actual evaluations
    # First collect meaningful non-generic strengths/weaknesses
    raw_strengths = []
    raw_weaknesses = []
    for e in evaluations:
        for s in (e.get("strengths") or []):
            s_clean = str(s).strip()
            if s_clean and s_clean.lower() not in ("provided an answer", "provided an answer.", "good detail"):
                raw_strengths.append(s_clean)
            elif s_clean.lower() in ("provided an answer", "provided an answer."):
                # replace generic with derived
                continue
            else:
                if s_clean:
                    raw_strengths.append(s_clean)
        for w in (e.get("weaknesses") or []):
            w_clean = str(w).strip()
            if w_clean and w_clean.lower() not in ("could provide more depth in some answers", "answer could be more detailed", "could be deeper", "answer could be more detailed."):
                raw_weaknesses.append(w_clean)
            elif w_clean:
                # keep but will be augmented with derived
                raw_weaknesses.append(w_clean)
            else:
                if w_clean:
                    raw_weaknesses.append(w_clean)
    # Derive strengths from dimension averages
    derived_strengths = []
    if tech >= 7:
        derived_strengths.append("Demonstrated good understanding of the technical concepts discussed.")
    if prob >= 7:
        derived_strengths.append("Explained project concepts with relevant implementation details.")
    if comm >= 7:
        derived_strengths.append("Communicated ideas clearly with structured explanations.")
    if relevance_avg >= 7:
        derived_strengths.append("Responses were well-aligned with the questions asked.")
    if avg >= 8 and tech >= 7 and comm >= 7:
        derived_strengths.append("Showed strong problem-solving approach with practical examples.")
    elif avg >= 7 and not derived_strengths:
        derived_strengths.append("Provided relevant and coherent responses across topics.")
    # Derive weaknesses from low dimensions
    derived_weaknesses = []
    if tech < 6:
        derived_weaknesses.append("Some answers showed gaps in technical understanding.")
    if prob < 6:
        derived_weaknesses.append("Some answers lacked implementation details.")
    if comm < 6:
        derived_weaknesses.append("Could improve clarity and structure in explanations.")
    if relevance_avg < 6:
        derived_weaknesses.append("Some responses were not fully aligned with the questions.")
    if avg < 6:
        derived_weaknesses.append("Some responses needed greater depth and concrete examples.")
    # Check inconsistency flag
    if any(e.get("inconsistency_flag") for e in evaluations):
        derived_weaknesses.append("Potential inconsistency between resume and answers noted.")
    # Merge raw and derived, deduplicate, prioritize derived meaningful ones
    strengths = []
    for s in derived_strengths + raw_strengths:
        if s not in strengths:
            # filter generic
            if s.lower() in ("provided an answer", "provided an answer.", "good detail", "good detail.", "participated thoroughly"):
                continue
            strengths.append(s)
        if len(strengths) >= 3:
            break
    weaknesses = []
    for w in derived_weaknesses + raw_weaknesses:
        if w not in weaknesses:
            # normalize generic
            if w.lower() in ("could provide more depth in some answers", "could provide more depth in some answers.", "answer could be more detailed"):
                # keep one instance as fallback but prefer derived
                if w not in derived_weaknesses:
                    continue
            weaknesses.append(w)
        if len(weaknesses) >= 3:
            break
    # Ensure at least one meaningful entry, but honestly reflect performance
    if not strengths:
        if avg >= 7:
            strengths = ["Provided relevant and coherent responses."]
        elif avg >= 5:
            strengths = ["Showed familiarity with relevant concepts in some responses."]
        else:
            strengths = ["Engaged in interview process"]
    if not weaknesses:
        if avg >= 8:
            weaknesses = []  # strong candidate may have no major weaknesses
        elif avg >= 7:
            weaknesses = ["Opportunities to add deeper technical nuance."]
        elif avg >= 5:
            weaknesses = ["Some answers could benefit from more concrete examples."]
        else:
            weaknesses = ["Responses needed greater depth and technical clarity."]
    # Ensure limits
    strengths = list(dict.fromkeys(strengths))[:3]
    weaknesses = list(dict.fromkeys(weaknesses))[:3]
    # Build meaningful summary based on actual performance
    if avg >= 8:
        summary = f"Candidate demonstrated strong performance with an average score of {avg:.1f}. Responses showed good technical understanding and clear communication. Recommendation: {rec}."
    elif avg >= 7:
        summary = f"Candidate showed good performance with an average score of {avg:.1f}. Technical explanations were generally relevant with clear examples. Recommendation: {rec}."
    elif avg >= 5:
        summary = f"Candidate showed adequate performance with an average score of {avg:.1f}. Some responses were relevant but lacked implementation details. Recommendation: {rec}."
    else:
        summary = f"Candidate's performance was below expectations with an average score of {avg:.1f}. Responses needed greater depth and technical clarity. Recommendation: {rec}."
    detailed = f"Average score {avg:.1f} across {len(evaluations)} questions (technical {tech:.1f}, communication {comm:.1f}, problem-solving {prob:.1f}) covering {', '.join(topics_covered[:4]) if topics_covered else 'general topics'}. "
    if strengths:
        detailed += f"Strengths included: {'; '.join(strengths[:2])}. "
    if weaknesses:
        detailed += f"Areas for improvement: {'; '.join(weaknesses[:2])}."
    return {
        "overall_score": int(round(avg)),
        "technical_score": int(round(tech)),
        "communication_score": int(round(comm)),
        "problem_solving_score": int(round(prob)),
        "strengths": strengths,
        "weaknesses": weaknesses,
        "topics_covered": topics_covered,
        "recommendation": rec,
        "summary": summary,
        "detailed_feedback": detailed.strip(),
    }
