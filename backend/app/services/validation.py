"""
Lightweight AI response validation — Phase 7.

No large model, no expensive pipeline, latency < 5ms (plus optional one retry).
Checks:
1. Empty
2. Malformed (prompt leakage, JSON artifacts, markdown breakage)
3. Refusal / error artifacts
4. Excessive repetition
5. Invalid structured output (where JSON expected)
6. Missing required fields (interview workflows)
7. Unsupported grounded claims (RAG)
"""
import re
import time
import json
from typing import Dict, List, Optional, Any, Tuple
import logging

logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# Thresholds / patterns — kept cheap, regex only
# ------------------------------------------------------------
REFUSAL_PATTERNS = [
    r"as an ai language model",
    r"i am an ai",
    r"i am unable to (?:provide|fulfill|answer|comply)",
    r"i cannot (?:provide|fulfill|comply|answer|assist)",
    r"sorry[, ]+i (?:cannot|am unable)",
    r"i don't have the ability",
    r"i am not able to",
]

ERROR_ARTIFACT_PATTERNS = [
    r"ollama.*unavailable",
    r"failed to connect",
    r"empty response from model",
    r"\b500\b.*error",
    r"internal server error",
    r"\btimeout\b",
    r"error:\s*.*ollama",
    r"model .* not available",
]

MALFORMED_PATTERNS = [
    r"<\|im_start\|>",
    r"<\|im_end\|>",
    r"assistant:\s*assistant:",
    r"user:\s*user:",
]

# For RAG grounded claim detection
GROUNDED_CLAIM_PATTERNS = [
    r"according to (?:the )?company (?:documents|policy|database|records)",
    r"according to (?:the )?retrieved (?:documents|context|information)",
    r"based on (?:the )?retrieved (?:documents|context)",
    r"based on (?:the )?company (?:documents|policy)",
    r"our company policy (?:states|is|requires)",
    r"samplecorp.*policy",
]

# Specific numeric company fact pattern (e.g., "24 days") — flagged only when rag_used False
NUMERIC_POLICY_PATTERN = r"\b\d+\s+days\b.*(?:paid|annual|leave|remote)"


def _word_count(text: str) -> int:
    return len(text.strip().split()) if text and text.strip() else 0


def check_empty(text: Optional[str]) -> Optional[str]:
    if text is None or not isinstance(text, str) or not text.strip():
        return "empty_response"
    # Do not flag short greetings as invalid; completeness is separate heuristic
    # Only truly empty is a hard failure; short but meaningful is allowed
    return None


def check_malformed(text: str, intent: Optional[str] = None) -> Optional[str]:
    if not text:
        return None
    low = text.lower()
    # Prompt leakage
    for pat in MALFORMED_PATTERNS:
        if re.search(pat, low):
            return f"malformed:prompt_leakage:{pat}"
    # JSON artifact in chat where not expected
    # If intent is not interview-related and text contains JSON object with typical keys, flag
    if intent not in ("interview",) and re.search(r"\{\s*\"(topics|question|overall_score|score)\"", text):
        return "malformed:unexpected_json"
    # Unclosed code fence
    if text.count("```") % 2 == 1:
        return "malformed:unclosed_code_fence"
    # Excessive JSON braces without being structured output
    if intent not in ("interview",) and text.strip().startswith("{") and text.strip().endswith("}"):
        try:
            json.loads(text)
            return "malformed:raw_json_instead_of_markdown"
        except Exception:
            pass
    # Contains HTML/script injection attempt
    if re.search(r"<script", low):
        return "malformed:html_injection"
    return None


def check_refusal_or_error(text: str) -> Optional[str]:
    if not text:
        return None
    low = text.lower()
    for pat in REFUSAL_PATTERNS:
        if re.search(pat, low):
            return f"refusal:{pat}"
    for pat in ERROR_ARTIFACT_PATTERNS:
        if re.search(pat, low):
            return f"error_artifact:{pat}"
    return None


def check_excessive_repetition(text: str) -> Optional[str]:
    if not text:
        return None
    # Char repetition (8+ same char) — check even for short texts
    if re.search(r"(.)\1{7,}", text):
        return "repetition:char_repeat"
    # Word repetition: same word 5 times in a row
    if re.search(r"\b(\w+)(?:\s+\1){4,}\b", text.lower()):
        return "repetition:word_repeat"
    if len(text) < 40:
        return None
    # Split words for n-gram check
    words = re.findall(r"\b\w+\b", text.lower())
    if len(words) >= 20:
        # Check 4-gram and 5-gram repeats
        for n in (4, 5):
            seen = {}
            for i in range(len(words) - n + 1):
                gram = " ".join(words[i:i+n])
                cnt = seen.get(gram, 0) + 1
                seen[gram] = cnt
                if cnt >= 4:
                    return f"repetition:{n}gram_repeat:{gram[:30]}"
    # Sentence repetition
    sentences = [s.strip().lower() for s in re.split(r"[.!?]+", text) if s.strip() and len(s.strip()) > 15]
    if len(sentences) >= 3:
        counts = {}
        for s in sentences:
            counts[s] = counts.get(s, 0) + 1
            if counts[s] >= 3:
                return "repetition:sentence_repeat"
            if counts[s] >= 2 and len(s.split()) > 8:
                # Two identical long sentences is suspicious
                return "repetition:sentence_duplicate"
    # Overall ratio: if 30% of words are same 3-word phrase, already caught by n-gram
    return None


def check_unsupported_grounded_claim(text: str, rag_used: bool, rag_results: Optional[List[Dict]] = None) -> Optional[str]:
    if not text:
        return None
    low = text.lower()
    # If response claims to be grounded but rag not used, flag
    for pat in GROUNDED_CLAIM_PATTERNS:
        if re.search(pat, low):
            if not rag_used:
                return f"unsupported_grounded_claim:{pat}"
            # If rag_used, check that response actually cites source
            # Minimal citation check: should contain "[Source:" or "Source:" when grounded
            # We don't fail if missing citation, but we note issue — for now not failing
            # To keep latency low and preserve good responses, only flag when rag_used False
            pass
    # Numeric policy claim without retrieval — heuristic for company-specific numbers
    # Example: "24 days of paid annual leave" when rag_used False
    if not rag_used and re.search(NUMERIC_POLICY_PATTERN, low):
        # Also check if text mentions company/policy context
        if any(k in low for k in ["company policy", "samplecorp", "paid annual leave", "remote work policy", "annual leave"]):
            return "unsupported_grounded_claim:numeric_policy_without_retrieval"
    # Avoid presenting unsupported company-specific info as fact when rag_used False
    # If text says "According to SampleCorp ..." without retrieval
    if not rag_used and re.search(r"according to samplecorp", low):
        return "unsupported_grounded_claim:samplecorp_without_retrieval"
    # Bare company factual claim without retrieval — detect assertions like "X is a Y", "X provides Z", "X offers..."
    # when rag_used=False and text mentions a proper-noun-like entity
    # Also catches "X operates under the name Y", "X is a company that..."
    if not rag_used:
        # Pattern 1: CapitalizedWord+ is a/an/provides/offers/has/operates... (handles periods in entity names)
        sentence_starters = {"here", "this", "that", "it", "our", "the", "a", "an", "there", "these", "those", "what", "which", "who", "where", "when", "why", "how"}
        bare_company_claim = re.search(
            r"\b([A-Z][a-z]+\.?(?:[ \t]+[A-Z][a-z]+\.?){0,3})[ \t]+(?:is|provides?|offers?|operates?|runs?|manages?|owns?|serves?)[ \t]+(?:a|an|the)[ \t]+",
            text
        )
        # Pattern 2: "X operates under the name" or "X is a company that..."
        broader_fabrication = re.search(
            r"\b([A-Z][a-z]+\.?(?:[ \t]+[A-Z][a-z]+\.?){0,3})[ \t]+(?:operates\s+under|is\s+a\s+company\s+that|is\s+a\s+leading|is\s+a\s+global)[ \t]+",
            text
        )
        claim_match = bare_company_claim or broader_fabrication
        if claim_match:
            entity = claim_match.group(1).strip().rstrip(".")
            # Skip common false positives (generic terms, not company names)
            generic_terms = {
                "company", "platform", "service", "system", "tool", "app", "website", "portal",
                "product", "solution", "organization", "business", "enterprise", "firm",
                "corporation", "corp", "inc", "ltd", "llc",
                # Political offices and public roles
                "president", "presidency", "prime minister", "governor", "senator",
                "senate", "congressman", "congresswoman", "representative",
                "chancellor", "secretary", "minister", "ambassador", "mayor",
                "vice president", "lieutenant governor", "attorney general",
                "sheriff", "commissioner", "judge", "justice", "chief justice",
                "cabinet", "administration", "officeholder", "white house",
                "capitol hill", "congress", "parliament", "democrat", "republican",
                "party", "election", "ballot", "campaign", "the president",
                "the prime minister", "the president of the", "campaign",
                # Well-known historical and public figures (surnames only)
                "obama", "trump", "biden", "clinton", "bush", "carter", "reagan",
                "nixon", "kennedy", "lincoln", "washington", "roosevelt",
                "churchill", "gandhi", "mandela", "king", "malala", "dalai",
                "gates", "jobs", "musk", "bezos", "buffett", "zuckerberg",
                "page", "brin", "nadella", "cook", "pichai", "sundar",
                "einstein", "newton", "curie", "tesla", "darwin", "hawking",
                "galileo", "da vinci", "michelangelo", "plato", "aristotle",
                "dickens", "shakespeare", "twain", "austen", "presley",
                "lennon", "mccartney", "jackson", "madonna", "swift",
                "beethoven", "mozart", "bach", "bacon", "edison", "bell",
                "lovelace", "turing", "shannon", "feynman", "tesla",
                "nobel", "marie curie", "charles darwin", "isaac newton",
                "albert einstein", "stephen hawking", "galileo galilei",
                "leonardo da vinci", "michelangelo", "winston churchill",
                "franklin roosevelt", "abraham lincoln", "george washington",
                "john f kennedy", "richard nixon", "ronald reagan",
                "jimmy carter", "bill clinton", "george bush", "barack obama",
                "donald trump", "joe biden", "bill gates", "steve jobs",
                "elon musk", "jeff bezos", "warren buffett", "mark zuckerberg",
                "larry page", "sergey brin", "satya nadella", "tim cook",
                "sundar pichai", "sam altman", "dario amodei",
                # Technology/programming languages/frameworks
                "python", "javascript", "java", "c++", "c#", "ruby", "php", "swift", "kotlin",
                "go", "rust", "typescript", "scala", "r", "matlab", "perl", "shell", "bash",
                "react", "vue", "angular", "django", "flask", "spring", "express", "fastapi",
                "tensorflow", "pytorch", "keras", "scikit", "pandas", "numpy", "sql", "nosql",
                "aws", "azure", "gcp", "docker", "kubernetes", "linux", "windows", "macos",
                "git", "github", "gitlab", "jenkins", "ci", "cd", "api", "rest", "graphql",
                "html", "css", "json", "xml", "yaml", "regex", "ai", "ml", "nlp", "cv",
                "llm", "gpt", "bert", "transformer", "neural", "deep", "machine", "learning",
                "data", "science", "analytics", "mining", "visualization", "statistics",
                # Common educational/scientific terms that start sentences
                "recursion", "photosynthesis", "artificial", "intelligence", "machine", "learning",
                "artificial intelligence", "machine learning", "deep learning",
                # Python-specific multi-word terms that commonly start sentences
                "python programming", "python language", "python script", "python code",
                "python interpreter", "python compiler", "python runtime", "python version",
                "python library", "python module", "python package", "python framework",
                "python developer", "python developer", "python programming language",
                "algorithm", "function", "variable", "object", "class", "method", "loop",
                "array", "list", "dictionary", "tree", "graph", "hash", "sort", "search",
                "database", "network", "protocol", "server", "client", "endpoint",
                "compiler", "interpreter", "runtime", "memory", "cpu", "gpu", "thread",
                "process", "async", "sync", "callback", "promise", "future", "await",
                "binary", "decimal", "hexadecimal", "octal", "bit", "byte", "word",
                "quantum", "computing", "qubit", "superposition", "entanglement",
                "cell", "molecule", "atom", "electron", "proton", "neutron", "dna",
                "rna", "protein", "enzyme", "gene", "chromosome", "genome", "evolution",
                "species", "organism", "ecosystem", "population", "community", "biome",
                "energy", "force", "mass", "velocity", "acceleration", "momentum",
                "gravity", "thermodynamics", "entropy", "equilibrium", "pressure",
                "temperature", "volume", "density", "concentration", "reaction",
                "catalyst", "reactant", "product", "yield", "rate", "constant", "law"
            }
            entity_lower = entity.lower()
            # Also skip if entity is a sentence starter
            if entity_lower in sentence_starters:
                return None
            # Skip if the response is hedging/admitting uncertainty rather than asserting a fact
            hedge_phrases = [
                "don't have", "do not have", "no information", "not aware",
                "cannot verify", "can't verify", "unable to verify",
                "i don't know", "not familiar", "no verified", "no data on",
                "not in my", "haven't been able to find",
                # Additional hedge phrases for qwen2.5 models
                "not sure", "not certain", "not confident", "not equipped",
                "i am not sure", "i am not certain", "i am not confident",
                "beyond my knowledge", "beyond my current knowledge",
                "beyond what i know", "beyond my training",
                "i cannot answer that", "i'm unable to answer",
                "not in a position to", "not equipped to answer",
                "i don't have enough information", "i lack information",
                "i don't have access to", "i don't have data on",
                "i'm not in a position", "that's not something i can",
                "i'm not able to verify", "i can't confirm",
                "i don't have verified", "i'm not equipped",
                "not something i can confirm", "not something i can verify",
                "i don't have sufficient", "i'm not sufficiently informed",
                "not aware of", "i'm not aware of",
                "can't say for certain", "can't say with certainty",
                "not in my training data", "not in my knowledge base",
            ]
            if any(h in low for h in hedge_phrases):
                return None
            if entity_lower not in generic_terms and len(entity) > 2:
                return f"unsupported_grounded_claim:bare_company_factual:{entity}"
    return None

def validate_chat_response(
    text: str,
    intent: Optional[str] = None,
    rag_used: bool = False,
    rag_results: Optional[List[Dict]] = None,
    message: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Lightweight chat validation. Returns dict with:
    - is_valid: bool
    - issues: List[str]
    - should_retry: bool (only for transient empty/malformed)
    - latency_ms: float
    """
    start = time.perf_counter()
    issues: List[str] = []

    # 1. Empty
    empty_issue = check_empty(text)
    if empty_issue:
        issues.append(empty_issue)
    else:
        # Only run other checks if not empty (avoid duplicate)
        # 2. Malformed
        mal = check_malformed(text, intent=intent)
        if mal:
            issues.append(mal)
        # 3. Refusal / error artifact
        ref = check_refusal_or_error(text)
        if ref:
            issues.append(ref)
        # 4. Repetition
        rep = check_excessive_repetition(text)
        if rep:
            issues.append(rep)
        # 7. Unsupported grounded claim
        ground = check_unsupported_grounded_claim(text, rag_used=rag_used, rag_results=rag_results)
        if ground:
            issues.append(ground)

    is_valid = len(issues) == 0
    # Retry only for transient issues where LLM might recover: empty or malformed prompt leakage
    should_retry = False
    if not is_valid:
        # Only retry for empty or malformed that is likely transient, not for repetition or grounded claim
        if any(i.startswith("empty") or i.startswith("too_short") or i.startswith("malformed:prompt") for i in issues):
            should_retry = True
        # Do not retry for refusal/error/repetition/grounded — fallback is better

    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    return {
        "is_valid": is_valid,
        "issues": issues,
        "should_retry": should_retry,
        "latency_ms": latency_ms,
    }


def get_safe_fallback(intent: Optional[str] = None, rag_used: bool = False, issues: Optional[List[str]] = None) -> str:
    """Provide safe, non-hallucinating fallback preserving intent."""
    base = "I apologize — I wasn't able to generate a complete response at the moment."
    # Check for bare company factual claim issue
    has_bare_company_claim = issues and any(i.startswith("unsupported_grounded_claim:bare_company_factual") for i in issues)
    if has_bare_company_claim:
        return base + " I don't have verified information about that company in my current knowledge sources. If you provide the company's details or documents, I can answer based on those."
    if intent == "career":
        return base + " Here's general career guidance: consider clarifying your current skills, target role, and timeline, and I can provide a phased plan (Now / Next 3 months / 12 months) with validation steps."
    if intent == "resume":
        return base + " For resume help, please share your target role and a pasted excerpt, and I can provide an ATS-friendly checklist and before→after bullet examples (without inventing scores)."
    if intent == "interview":
        return base + " For interview prep, I can provide role-specific example questions, STAR framework guidance, and 3–5 preparation steps. Please specify the role/level for tailored practice."
    if intent == "learning":
        return base + " For learning guidance, please share your goal, current level, and timeline, and I can provide a phased roadmap (Fundamentals → Intermediate → Advanced) with projects and evaluation criteria."
    if intent == "recruitment":
        return base + " For recruitment support, I can help draft a structured job description, must-have vs nice-to-have, and screening checklist. Please share the role and team context."
    if intent == "business":
        return base + " For business queries, I can provide a brief diagnostic framework and 3–5 specific steps. Please share team size, process, and constraints for tailored advice."
    if rag_used:
        # When grounded was expected but failed, be explicit
        return base + " No approved documents were found that directly answer your query, but I can provide general best-practice guidance. Please provide more details for a grounded answer when available."
    return base + " Please try rephrasing your question, and I'll provide general best-practice guidance (without claiming live browsing or proprietary data)."


# ------------------------------------------------------------
# Interview structured output validation (lightweight)
# ------------------------------------------------------------

def validate_plan(data: Any, job_title: str = "") -> Tuple[bool, List[str], Optional[str]]:
    """Validate interview plan structure. Returns (is_valid, issues, fallback_hint)."""
    issues: List[str] = []
    if not isinstance(data, dict):
        return False, ["missing:plan_not_dict"], "plan"
    topics = data.get("topics") or data.get("plan") or data.get("interview_plan")
    if not isinstance(topics, list):
        return False, ["missing:topics_not_list"], "plan"
    if len(topics) < 5:
        issues.append(f"invalid:too_few_topics:{len(topics)}")
    if len(topics) > 10:
        issues.append(f"invalid:too_many_topics:{len(topics)}")
    # Each topic should have name
    for i, t in enumerate(topics):
        if isinstance(t, dict):
            if not t.get("name") or not str(t.get("name")).strip():
                issues.append(f"missing:topic_{i}_name")
        elif isinstance(t, str):
            if not t.strip():
                issues.append(f"missing:topic_{i}_empty_str")
        else:
            issues.append(f"invalid:topic_{i}_type")
    is_valid = len(issues) == 0 or all("missing:topic" not in x for x in issues)
    # If only count issues, still consider valid enough? We treat <5 as invalid requiring fallback
    if any("too_few_topics" in x for x in issues):
        return False, issues, "plan"
    return len(issues) == 0, issues, None


def validate_question(data: Any, question_number: Optional[int] = None) -> Tuple[bool, List[str], Optional[str]]:
    issues: List[str] = []
    if not isinstance(data, dict):
        return False, ["missing:question_not_dict"], "question"
    q = data.get("question") or data.get("text") or ""
    if not isinstance(q, str) or len(q.strip()) < 10:
        issues.append("missing:question_text_too_short")
    topic = data.get("topic")
    if not topic or not str(topic).strip():
        issues.append("missing:topic")
    diff = str(data.get("difficulty", "")).lower()
    if diff not in ("easy", "medium", "hard", ""):
        issues.append(f"invalid:difficulty:{diff}")
    if question_number is not None and data.get("question_number") not in (None, question_number):
        # Allow mismatch but note
        pass
    if "is_follow_up" in data and not isinstance(data["is_follow_up"], bool):
        issues.append("invalid:is_follow_up_not_bool")
    is_valid = len([x for x in issues if x.startswith("missing:question")]) == 0
    return is_valid, issues, None if is_valid else "question"


def validate_final_report(data: Any, topics_covered: Optional[List[str]] = None) -> Tuple[bool, List[str], Optional[str]]:
    issues: List[str] = []
    if not isinstance(data, dict):
        return False, ["missing:report_not_dict"], "report"
    required = ["overall_score", "technical_score", "communication_score", "problem_solving_score", "strengths", "weaknesses", "recommendation", "summary"]
    for field in required:
        if field not in data:
            issues.append(f"missing:{field}")
        elif field.endswith("_score"):
            try:
                v = int(data[field])
                if not (0 <= v <= 10):
                    issues.append(f"invalid:{field}_out_of_range:{v}")
            except Exception:
                issues.append(f"invalid:{field}_not_int")
        elif field in ("strengths", "weaknesses"):
            if not isinstance(data[field], list):
                issues.append(f"invalid:{field}_not_list")
        elif field in ("recommendation", "summary"):
            if not isinstance(data[field], str) or not data[field].strip():
                issues.append(f"missing:{field}_empty")
    if topics_covered is not None and "topics_covered" not in data:
        issues.append("missing:topics_covered")
    # Any missing required or invalid score makes report invalid
    is_valid = len(issues) == 0
    return is_valid, issues, None if is_valid else "report"


def validate_evaluation(data: Any) -> Tuple[bool, List[str], Optional[str]]:
    issues: List[str] = []
    if not isinstance(data, dict):
        return False, ["missing:evaluation_not_dict"], "evaluation"
    for field in ["score", "correctness", "relevance", "depth", "clarity"]:
        if field not in data:
            issues.append(f"missing:{field}")
        else:
            try:
                v = int(data[field])
                if not (0 <= v <= 10):
                    issues.append(f"invalid:{field}_range:{v}")
            except Exception:
                issues.append(f"invalid:{field}_not_int")
    if "follow_up_needed" in data and not isinstance(data["follow_up_needed"], bool):
        issues.append("invalid:follow_up_needed_not_bool")
    return len(issues) == 0, issues, None
