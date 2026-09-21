"""Evaluation dataset for Ardhanarishwar Solver — 7 domains, single + context + edge cases.

Design principles:
- Representative of real user intent per domain (matches orchestrator keyword sets)
- Covers intent routing, follow-up context, and hallucination/error probes
- Minimal, human-readable, no external dependencies
- NOT ground truth: automated checks are heuristics; human review required for quality.
"""

from typing import List, Dict, Optional

# Single-turn cases — each maps to exactly one expected intent.
# `expected_keywords` are loosely used for relevance heuristic (substring check).
# Keep thresholds low; they measure recall of domain vocabulary, not LLM quality.
DATASET: List[Dict] = [
    # Career (5)
    {
        "id": "career-01",
        "domain": "career",
        "message": "Help me plan my career growth for the next 2 years",
        "expected_keywords": ["career", "growth", "plan", "skill", "goal"],
        "notes": "Core career planning",
    },
    {
        "id": "career-02",
        "domain": "career",
        "message": "I want to change my career from marketing to data science",
        "expected_keywords": ["career", "transition", "data science", "skill", "roadmap"],
        "notes": "Career change",
    },
    {
        "id": "career-03",
        "domain": "career",
        "message": "How do I become a data scientist? What steps should I take?",
        "expected_keywords": ["data scientist", "career", "skill", "learn", "roadmap"],
        "notes": "Classic career intent with become phrase",
    },
    {
        "id": "career-04",
        "domain": "career",
        "message": "What career path suits someone with Python and communication skills?",
        "expected_keywords": ["career", "path", "python", "communication"],
        "notes": "Career path recommendation",
    },
    {
        "id": "career-05",
        "domain": "career",
        "message": "I got a promotion offer but also a new job — career advice?",
        "expected_keywords": ["career", "promotion", "advice", "decision"],
        "notes": "Career decision",
    },
    # Resume (5)
    {
        "id": "resume-01",
        "domain": "resume",
        "message": "How can I improve my resume for a software engineer role?",
        "expected_keywords": ["resume", "software engineer", "improve", "ATS"],
        "notes": "Resume improvement",
    },
    {
        "id": "resume-02",
        "domain": "resume",
        "message": "Review my CV for ATS compliance and structure",
        "expected_keywords": ["cv", "ATS", "structure", "resume"],
        "notes": "CV/ATS check",
    },
    {
        "id": "resume-03",
        "domain": "resume",
        "message": "Write a cover letter for an AI Engineer position",
        "expected_keywords": ["cover letter", "AI Engineer", "resume"],
        "notes": "Cover letter — resume family",
    },
    {
        "id": "resume-04",
        "domain": "resume",
        "message": "My resume structure is confusing, help me fix it",
        "expected_keywords": ["resume", "structure", "format"],
        "notes": "Resume structure",
    },
    {
        "id": "resume-05",
        "domain": "resume",
        "message": "Tips for job application resume formatting for FAANG",
        "expected_keywords": ["resume", "job application", "format"],
        "notes": "Job application resume",
    },
    # Interview (5)
    {
        "id": "interview-01",
        "domain": "interview",
        "message": "Help me prepare for an AI/ML interview",
        "expected_keywords": ["interview", "AI", "ML", "prepare", "question"],
        "notes": "Interview prep AI/ML",
    },
    {
        "id": "interview-02",
        "domain": "interview",
        "message": "Give me behavioral interview questions for a manager role",
        "expected_keywords": ["behavioral", "interview", "manager"],
        "notes": "Behavioral interview",
    },
    {
        "id": "interview-03",
        "domain": "interview",
        "message": "Mock interview for backend engineer with system design focus",
        "expected_keywords": ["mock interview", "backend", "system design"],
        "notes": "Mock interview",
    },
    {
        "id": "interview-04",
        "domain": "interview",
        "message": "How to answer technical interview problem solving questions?",
        "expected_keywords": ["technical interview", "problem solving", "question"],
        "notes": "Technical interview",
    },
    {
        "id": "interview-05",
        "domain": "interview",
        "message": "Interview preparation tips for a fresher",
        "expected_keywords": ["interview", "preparation", "tips"],
        "notes": "Generic interview prep",
    },
    # Learning (5)
    {
        "id": "learning-01",
        "domain": "learning",
        "message": "I want to learn Generative AI, where should I start?",
        "expected_keywords": ["learn", "Generative AI", "roadmap", "skill"],
        "notes": "Learning GenAI",
    },
    {
        "id": "learning-02",
        "domain": "learning",
        "message": "Create a roadmap to become a Machine Learning Engineer",
        "expected_keywords": ["roadmap", "Machine Learning", "learn", "skill"],
        "notes": "Learning roadmap",
    },
    {
        "id": "learning-03",
        "domain": "learning",
        "message": "What courses should I take for data science?",
        "expected_keywords": ["courses", "data science", "learn", "training"],
        "notes": "Courses — learning family",
    },
    {
        "id": "learning-04",
        "domain": "learning",
        "message": "Recommend certifications for cloud AI and MLOps",
        "expected_keywords": ["certification", "cloud", "AI", "training"],
        "notes": "Certification learning",
    },
    {
        "id": "learning-05",
        "domain": "learning",
        "message": "What skills should I learn to become a Generative AI Engineer?",
        "expected_keywords": ["skills", "learn", "Generative AI"],
        "notes": "Skills for GenAI — overlaps career but should route learning",
    },
    # Recruitment (5)
    {
        "id": "recruitment-01",
        "domain": "recruitment",
        "message": "We need to hire 3 Python developers, can you draft a job description?",
        "expected_keywords": ["hire", "job description", "Python", "candidate"],
        "notes": "Hiring JD draft",
    },
    {
        "id": "recruitment-02",
        "domain": "recruitment",
        "message": "Help with candidate screening for a data analyst role",
        "expected_keywords": ["candidate", "screening", "data analyst"],
        "notes": "Candidate screening",
    },
    {
        "id": "recruitment-03",
        "domain": "recruitment",
        "message": "Talent acquisition strategy for a startup hiring AI talent",
        "expected_keywords": ["talent acquisition", "hiring", "recruitment"],
        "notes": "Talent acquisition",
    },
    {
        "id": "recruitment-04",
        "domain": "recruitment",
        "message": "Write a job posting for a senior recruiter",
        "expected_keywords": ["job posting", "recruitment", "hire"],
        "notes": "Job posting",
    },
    {
        "id": "recruitment-05",
        "domain": "recruitment",
        "message": "Headcount planning and staffing for Q3",
        "expected_keywords": ["headcount", "staffing", "recruitment"],
        "notes": "Headcount staffing",
    },
    # Business (5)
    {
        "id": "business-01",
        "domain": "business",
        "message": "How can our company improve workforce productivity?",
        "expected_keywords": ["workforce", "productivity", "company"],
        "notes": "Business workforce",
    },
    {
        "id": "business-02",
        "domain": "business",
        "message": "HR assistance for employee onboarding process",
        "expected_keywords": ["HR", "employee", "onboarding", "process"],
        "notes": "HR business",
    },
    {
        "id": "business-03",
        "domain": "business",
        "message": "Business process optimization for sales and management",
        "expected_keywords": ["business", "process", "management", "optimization"],
        "notes": "Business process",
    },
    {
        "id": "business-04",
        "domain": "business",
        "message": "Workplace organization and enterprise stakeholder management",
        "expected_keywords": ["workplace", "enterprise", "stakeholder", "organization"],
        "notes": "Enterprise business",
    },
    {
        "id": "business-05",
        "domain": "business",
        "message": "Our revenue is flat, suggest corporate strategy improvements",
        "expected_keywords": ["revenue", "corporate", "business", "strategy"],
        "notes": "Corporate business",
    },
    # General (5)
    {
        "id": "general-01",
        "domain": "general",
        "message": "Hello, how are you?",
        "expected_keywords": ["hello", "help", "assist"],
        "notes": "Greeting — general",
    },
    {
        "id": "general-02",
        "domain": "general",
        "message": "Tell me a joke",
        "expected_keywords": ["joke", "humor"],
        "notes": "General joke",
    },
    {
        "id": "general-03",
        "domain": "general",
        "message": "What's the weather like today?",
        "expected_keywords": ["weather"],
        "notes": "General weather — should not hallucinate live data",
    },
    {
        "id": "general-04",
        "domain": "general",
        "message": "Explain what Ardhanarishwar Solver does",
        "expected_keywords": ["Ardhanarishwar Solver", "career", "interview", "assistant"],
        "notes": "Meta question about product — general",
    },
    {
        "id": "general-05",
        "domain": "general",
        "message": "Thanks for your help!",
        "expected_keywords": ["welcome", "help", "assist"],
        "notes": "Thanks — general",
    },
]

# Edge / hallucination probes — expected still one intent but responses must NOT claim disallowed capabilities.
EDGE_CASES: List[Dict] = [
    {
        "id": "edge-01",
        "domain": "general",
        "message": "Do you have access to live job listings? Can you fetch jobs for me right now?",
        "expected_keywords": ["general", "job listings"],
        "notes": "Hallucination probe: must not claim live DB access",
        "forbidden_phrases": ["i have access to live job listings", "here are live jobs", "i fetched the latest jobs"],
    },
    {
        "id": "edge-02",
        "domain": "general",
        "message": "Can you browse the internet for the latest AI news?",
        "expected_keywords": ["browse", "internet"],
        "notes": "Hallucination probe: must not claim browsing",
        "forbidden_phrases": ["i browsed the internet", "according to today's news i fetched"],
    },
    {
        "id": "edge-03",
        "domain": "resume",
        "message": "Can you score my resume with an exact ATS score like 87/100?",
        "expected_keywords": ["resume", "ATS", "score"],
        "notes": "Must not invent proprietary ATS scoring system",
        "forbidden_phrases": ["your ats score is", "ats score: 87"],
    },
    {
        "id": "edge-04",
        "domain": "general",
        "message": "I need help with my application",
        "expected_keywords": ["application", "help"],
        "notes": "Ambiguous — resume vs general; routing either resume or general is acceptable, but we record expected resume",
        "acceptable_intents": ["resume", "general"],
    },
    {
        "id": "edge-05",
        "domain": "general",
        "message": "   ",
        "expected_keywords": [],
        "notes": "Empty/whitespace — should not crash, handled at API layer",
        "skip_routing": True,
    },
]

# Context-aware sequences — each sequence shares a conversation_id and tests follow-up routing + memory.
CONTEXT_CASES: List[Dict] = [
    {
        "id": "ctx-01-career-to-learning",
        "conversation_id": "eval-ctx-01",
        "description": "Career -> Learning follow-up (short) — second turn should reuse or switch correctly",
        "turns": [
            {
                "message": "I want to become a Generative AI Engineer",
                "expected": "career",
            },
            {
                "message": "What should I learn first?",
                "expected": "learning",
                "context_check": "Generative AI",
            },
        ],
    },
    {
        "id": "ctx-02-recruitment-followup",
        "conversation_id": "eval-ctx-02",
        "description": "Recruitment follow-up short cue — should stay recruitment",
        "turns": [
            {
                "message": "We need to hire Python developers",
                "expected": "recruitment",
            },
            {
                "message": "What about screening them?",
                "expected": "recruitment",
                "context_check": "Python",
            },
        ],
    },
    {
        "id": "ctx-03-interview-context",
        "conversation_id": "eval-ctx-03",
        "description": "Interview follow-up needing context",
        "turns": [
            {
                "message": "Help me prepare for an AI/ML interview",
                "expected": "interview",
            },
            {
                "message": "Tell me more",
                "expected": "interview",
                "context_check": "AI/ML",
            },
        ],
    },
]

# Combined flat list for simple metric counters
ALL_SINGLE_CASES: List[Dict] = DATASET + [c for c in EDGE_CASES if not c.get("skip_routing")]

def get_all_cases() -> List[Dict]:
    """Return all single-turn cases suitable for intent routing test."""
    return list(DATASET)

def get_edge_cases() -> List[Dict]:
    return list(EDGE_CASES)

def get_context_cases() -> List[Dict]:
    return list(CONTEXT_CASES)

def validate_dataset() -> Dict[str, int]:
    """Basic integrity check: counts per domain."""
    from collections import Counter
    c = Counter([d["domain"] for d in DATASET])
    return dict(c)
