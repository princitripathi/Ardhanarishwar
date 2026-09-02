import asyncio
import pytest
from app.services.orchestrator import detect_intent


@pytest.mark.parametrize("message, expected", [
    ("What career should I choose?", "career"),
    ("I want to change my career path", "career"),
    ("How do I become a data scientist?", "career"),
    ("What is my professional future?", "career"),
])
def test_career_intent(message, expected):
    assert detect_intent(message) == expected


@pytest.mark.parametrize("message, expected", [
    ("Improve my resume", "resume"),
    ("Help me update my CV", "resume"),
    ("I need ATS recommendations", "resume"),
    ("Write a cover letter", "resume"),
    ("My resume structure is bad", "resume"),
])
def test_resume_intent(message, expected):
    assert detect_intent(message) == expected


@pytest.mark.parametrize("message, expected", [
    ("Give me Python interview questions", "interview"),
    ("Prepare me for a technical interview", "interview"),
    ("Behavioral interview tips", "interview"),
    ("Mock interview for software engineer", "interview"),
])
def test_interview_intent(message, expected):
    assert detect_intent(message) == expected


@pytest.mark.parametrize("message, expected", [
    ("What should I learn for Generative AI?", "learning"),
    ("What skills should I learn to become a Generative AI Engineer?", "learning"),
    ("I want to learn Python", "learning"),
    ("Create a learning roadmap for AI", "learning"),
    ("What courses should I take?", "learning"),
])
def test_learning_intent(message, expected):
    assert detect_intent(message) == expected


@pytest.mark.parametrize("message, expected", [
    ("We need to hire Python developers", "recruitment"),
    ("Help with hiring", "recruitment"),
    ("I need candidate screening help", "recruitment"),
    ("Write a job description", "recruitment"),
    ("Recruitment planning for our team", "recruitment"),
])
def test_recruitment_intent(message, expected):
    assert detect_intent(message) == expected


@pytest.mark.parametrize("message, expected", [
    ("How can a company improve workforce productivity?", "business"),
    ("How can our company improve employee productivity?", "business"),
    ("HR assistance needed", "business"),
    ("Workforce planning strategies", "business"),
    ("How to improve business processes?", "business"),
])
def test_business_intent(message, expected):
    assert detect_intent(message) == expected


@pytest.mark.parametrize("message, expected", [
    ("Hello, how are you?", "general"),
    ("Hi there!", "general"),
    ("What's the weather like?", "general"),
    ("Tell me a joke", "general"),
])
def test_general_intent(message, expected):
    assert detect_intent(message) == expected