import logging
from typing import Dict

from app.services.llm import generate_response, OllamaError
from app.interview.prompts import EVALUATOR_SYSTEM_PROMPT
from app.interview.llm_helpers import extract_json, normalize_evaluation

logger = logging.getLogger(__name__)


async def evaluate_answer(
    question: Dict,
    answer: str,
    resume_text: str,
    job_description: str,
    topic: str = "",
) -> Dict:
    """Evaluate candidate answer using LLM, with fallback to heuristic."""
    q_text = question.get("question", "") if isinstance(question, dict) else str(question)
    prompt = f"""Question: {q_text}
Topic: {topic or question.get('topic','General') if isinstance(question, dict) else 'General'}
Difficulty: {question.get('difficulty','medium') if isinstance(question, dict) else 'medium'}

Candidate Answer:
{answer}

Resume (excerpt):
{resume_text[:1500]}

Job Description (excerpt):
{job_description[:1500]}

Evaluate and return JSON only.
"""

    try:
        resp = await generate_response(prompt, system_prompt=EVALUATOR_SYSTEM_PROMPT)
        raw = extract_json(resp.response)
        if raw is None:
            logger.warning(f"Evaluator JSON parse failed, raw: {resp.response[:500]}")
            return _heuristic_eval(answer)
        normalized = normalize_evaluation(raw)
        # Additional inconsistency check heuristic overlay
        inconsistency = _detect_inconsistency(answer, resume_text)
        if inconsistency and not normalized["inconsistency_flag"]:
            normalized["inconsistency_flag"] = True
            normalized["inconsistency_note"] = inconsistency
        return normalized
    except OllamaError as e:
        logger.error(f"Evaluator OllamaError: {e.message}")
        return _heuristic_eval(answer, ollama_unavailable=True)
    except Exception as e:
        logger.exception("Evaluator unexpected error")
        return _heuristic_eval(answer)


def _detect_inconsistency(answer: str, resume_text: str) -> str | None:
    """Simple keyword-based inconsistency detection."""
    if not answer or not resume_text:
        return None
    lower_ans = answer.lower()
    lower_resume = resume_text.lower()
    # If answer says never used / no experience with something prominent in resume
    denial_phrases = ["never used", "never worked with", "i have never", "no experience with", "don't know", "do not know"]
    has_denial = any(p in lower_ans for p in denial_phrases)
    if has_denial:
        # extract tech keywords from resume
        tech_keywords = ["python", "java", "javascript", "fastapi", "react", "sql", "faiss", "pytorch", "tensorflow", "docker", "aws", "llm", "machine learning", "deep learning"]
        for kw in tech_keywords:
            if kw in lower_resume and kw in lower_ans:
                return "Potential inconsistency between the candidate's answer and resume."
        # generic if denial + resume present
        if has_denial:
            return "Potential inconsistency between the candidate's answer and resume."
    return None


def _heuristic_eval(answer: str, ollama_unavailable: bool = False) -> Dict:
    if not answer or not answer.strip():
        return {
            "score": 2,
            "correctness": 2,
            "relevance": 2,
            "depth": 2,
            "clarity": 2,
            "feedback": "No answer was provided for evaluation.",
            "strengths": [],
            "weaknesses": ["No answer provided.", "Could provide more depth in some answers."],
            "follow_up_needed": True,
            "inconsistency_flag": False,
            "inconsistency_note": None,
            "difficulty_adjustment": "decrease",
        }
    words = len(answer.split())
    sentences = answer.count(".") + answer.count("!") + answer.count("?") + answer.count(";")
    lower = answer.lower()
    has_example = any(k in lower for k in ["for example", "e.g.", "for instance", "such as", "like when", "for ex"])
    has_project_detail = any(k in lower for k in ["project", "implemented", "built", "designed", "developed", "created", "deployed", "engineered", "migrated", "optimized"])
    has_technical = any(k in lower for k in ["python", "sql", "api", "system", "algorithm", "model", "framework", "database", "architecture", "pipeline", "service", "function", "class", "component"])
    has_tradeoff = any(k in lower for k in ["trade-off", "tradeoff", "advantage", "disadvantage", "pros", "cons", "versus", "compared", "alternative", "choice", "decision"])
    has_metrics = any(k in lower for k in ["%", "improved", "reduced", "increased", "latency", "throughput", "accuracy", "performance", "result", "outcome"])
    if words < 10:
        score = 4
    elif words < 30:
        score = 6
    elif words < 80:
        score = 7
    else:
        score = 8
    if has_example and has_project_detail:
        score = min(10, score + 1)
    elif has_example and words >= 20:
        score = min(10, score + 1)
    correctness = score
    relevance = score
    depth = max(2, score - 1)
    if has_example and has_project_detail:
        depth = min(10, depth + 1)
    elif words < 20:
        depth = max(2, depth - 1)
    clarity = score
    if sentences >= 3 and words >= 30:
        clarity = min(10, clarity + 1)
    elif words < 15:
        clarity = max(2, clarity - 1)
    strengths = []
    if score >= 7:
        if has_project_detail:
            strengths.append("Explained project concepts with relevant implementation details.")
        if has_example:
            strengths.append("Provided concrete examples to support explanations.")
        if has_technical:
            strengths.append("Demonstrated good understanding of the technical concepts discussed.")
        if has_metrics:
            strengths.append("Quantified outcomes and highlighted measurable impact.")
        if has_tradeoff:
            strengths.append("Explained technical trade-offs with clear reasoning.")
        if sentences >= 3 and clarity >= 7:
            strengths.append("Communicated ideas with clear structure and coherence.")
        if not strengths:
            strengths.append("Provided relevant and coherent response addressing the question.")
    elif score >= 5:
        if has_project_detail or has_example:
            strengths.append("Included relevant project details in response.")
        if has_technical:
            strengths.append("Showed familiarity with relevant technical concepts.")
        if not strengths:
            strengths.append("Provided a relevant answer to the question.")
    weaknesses = []
    if score < 7:
        if not has_project_detail:
            weaknesses.append("Some answers lacked implementation details.")
        if not has_example:
            weaknesses.append("Could include more concrete examples.")
        if words < 30:
            weaknesses.append("Some responses needed greater depth.")
        if not has_tradeoff and score <= 6:
            weaknesses.append("Could explain technical trade-offs more clearly.")
        if clarity < 6:
            weaknesses.append("Could improve clarity and structure in explanations.")
        if has_technical and depth < 6:
            weaknesses.append("Technical explanations could be more thorough.")
    if not weaknesses and score >= 7 and score < 8:
        weaknesses.append("Opportunities to add deeper technical nuance.")
    strengths = list(dict.fromkeys(strengths))[:3]
    weaknesses = list(dict.fromkeys(weaknesses))[:3]
    if not strengths and score >= 5:
        strengths = ["Provided a relevant answer to the question."]
    if score >= 8 and not weaknesses:
        weaknesses = []
    elif score >= 7 and not weaknesses:
        weaknesses = ["Could provide even deeper elaboration on complex topics."]
    elif score < 7 and not weaknesses:
        weaknesses = ["Could provide more depth in some answers."]
    correctness = int(round(correctness))
    relevance = int(round(relevance))
    depth = int(round(depth))
    clarity = int(round(clarity))
    if score >= 8:
        feedback = "Strong response with good technical detail and clear examples."
    elif score >= 7:
        feedback = "Good response with relevant details and coherent explanation."
    elif score >= 5:
        feedback = "Adequate response but could benefit from more depth and concrete examples."
    else:
        feedback = "Response was brief and lacked sufficient detail and examples."
    if ollama_unavailable:
        feedback = feedback + " (LLM unavailable, heuristic evaluation)"
    return {
        "score": score,
        "correctness": correctness,
        "relevance": relevance,
        "depth": depth,
        "clarity": clarity,
        "feedback": feedback,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "follow_up_needed": score < 6,
        "inconsistency_flag": False,
        "inconsistency_note": None,
        "difficulty_adjustment": "decrease" if score < 5 else "increase" if score >= 8 else "maintain",
    }
