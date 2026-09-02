# Ardhanarishwar

### AI-Powered Career, Recruitment & Interview Assistant

Ardhanarishwar is an AI-powered platform that combines career guidance, resume assistance, interview preparation, learning support, and recruitment workflows into a single application. It uses locally hosted large language models through Ollama, specialized AI agents with intent-based routing, and an adaptive AI interview system with voice interaction and browser-level proctoring.

---

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" alt="React">
  <img src="https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white" alt="Vite">
  <img src="https://img.shields.io/badge/Ollama-Qwen2.5_3B-FFFFFF?logo=ollama&logoColor=black" alt="Ollama">
  <img src="https://img.shields.io/badge/Tests-129%20passed-4CAF50?logo=pytest&logoColor=white" alt="Tests">
</p>

---

## Demo

<p align="center">
  <a href="./demo_video.mp4">
    <img src="./interview_feedback.png" alt="AI Interview Feedback Report" width="700">
  </a>
  <br>
  <a href="./demo_video.mp4"><strong>&#9654; Watch the Demo</strong></a>
  <br>
  <em>Screenshot: AI interview feedback report with scoring, strengths, weaknesses, and recommendation.</em>
</p>

---

## Overview

Ardhanarishwar brings together several AI-driven workflows into one coherent platform:

- **Generative AI** via a locally hosted Qwen2.5 3B model through Ollama
- **Specialized AI agents** for career, resume, interview, learning, recruitment, and business domains
- **Intent-based orchestration** that routes user messages to the appropriate agent
- **Short-term conversation memory** with bounded context management
- **AI-powered interview workflow** with dynamic question generation, answer evaluation, and adaptive difficulty
- **Voice interaction** using browser Speech Recognition and Speech Synthesis APIs
- **Browser-level proctoring** for interview integrity monitoring

The current prototype runs entirely on local infrastructure using Ollama, requiring no commercial AI API keys.

---

## Problem Statement

Candidates and professionals often need separate tools for career guidance, learning, resume preparation, and interview practice. Recruiters need structured interview scheduling, candidate evaluation, and feedback workflows. Ardhanarishwar attempts to consolidate these workflows into a single AI-powered platform with a unified conversational interface.

---

## Key Features

| Category | Feature | Description |
|----------|---------|-------------|
| **AI Assistant** | Conversational Chat | Streaming and non-streaming AI chat with markdown rendering |
| | Intent Detection | Keyword-based routing to specialized agents |
| | Conversation Memory | Bounded short-term memory per conversation |
| **Career** | Career Guidance | Career planning, job search strategy, professional development |
| **Resume** | Resume Assistance | Resume improvement, ATS recommendations, cover letter guidance |
| **Interview** | Interview Preparation | Mock interviews, behavioral and technical prep |
| | AI Interview System | End-to-end automated interview with plan generation |
| | Dynamic Questions | LLM-generated questions adapted to role and resume |
| | Answer Evaluation | Multi-dimensional scoring with heuristic fallback |
| | Adaptive Flow | Difficulty adjusts based on candidate performance |
| | Final Report | Comprehensive scoring with strengths, weaknesses, recommendation |
| **Learning** | Learning Guidance | Skill development paths, course recommendations, roadmaps |
| **Recruitment** | Recruitment Support | Job description drafting, candidate screening workflows |
| **Business** | Business Assistance | Workforce planning, HR process guidance |
| **Voice** | Speech-to-Text | Browser Web Speech API for voice-based answers |
| | Text-to-Speech | AI reads questions aloud using Speech Synthesis |
| **Proctoring** | Tab Monitoring | Tracks tab focus/blur events |
| | Fullscreen Enforcement | Monitors fullscreen status |
| | Camera/Mic Status | Monitors media stream integrity |
| | Event Logging | Records all proctoring events with severity levels |
| **Streaming** | NDJSON Streaming | Server-sent streaming with metadata and chunk events |
| **Reliability** | Heuristic Fallbacks | Code-based fallbacks when LLM is unavailable |

---

## AI Architecture

```
User
 |
 v
React Frontend  <----->  FastAPI Backend
                             |
                        Orchestrator
                             |
                    +--------+--------+
                    |                 |
              Intent Detection   Conversation
              (keyword-based)    Memory
                    |                 |
                    v                 v
            Specialized Agent    Context
            (system prompt)      Building
                    |
                    v
              LLM Service
              (httpx async)
                    |
                    v
               Ollama API
                    |
                    v
            Qwen2.5 3B (local)
                    |
                    v
              Response Stream
```

**Components:**

| Component | Location | Role |
|-----------|----------|------|
| **React Frontend** | `frontend/src/` | Chat UI, interview workspace, voice/proctoring |
| **FastAPI Backend** | `backend/app/main.py` | API server, CORS, route registration |
| **Orchestrator** | `backend/app/services/orchestrator.py` | Intent detection, agent routing, context management |
| **Conversation Memory** | `backend/app/services/conversation_memory.py` | In-memory bounded message history |
| **LLM Service** | `backend/app/services/llm.py` | Ollama HTTP integration, streaming, health checks |
| **Agents** | `backend/app/agents/` | Six domain-specialized agents |
| **Interview Engine** | `backend/app/interview/engine.py` | Plan generation, question generation, final reports |
| **Evaluator** | `backend/app/interview/evaluator.py` | LLM-based answer evaluation with heuristic fallback |

---

## Agentic Architecture

Ardhanarishwar uses an **agent-oriented architecture** with specialized agents and a central orchestrator. Each agent is a lightweight module with a domain-specific system prompt that guides the LLM's responses for that particular workflow.

### Specialized Agents

| Agent | Module | Responsibility |
|-------|--------|----------------|
| **Career Advisor** | `career_agent.py` | Career planning, job search, professional development |
| **Resume Advisor** | `resume_agent.py` | Resume/CV improvement, ATS optimization, cover letters |
| **Interview Coach** | `interview_agent.py` | Interview preparation, mock interviews, tips |
| **Learning Advisor** | `learning_agent.py` | Skill development, training paths, course guidance |
| **Recruitment Advisor** | `recruitment_agent.py` | Hiring support, job descriptions, screening |
| **Business Advisor** | `business_agent.py` | Business problems, workforce planning, HR processes |

### Orchestrator

The orchestrator (`orchestrator.py`) handles:

1. **Intent Detection** -- Keyword-based regex matching with priority ordering
2. **Contextual Follow-up** -- Reuses previous intent for short follow-up messages
3. **Agent Routing** -- Lazy-loads the appropriate agent and delegates the request
4. **Memory Management** -- Stores messages and builds context from conversation history
5. **Streaming** -- Routes streaming requests with intent-specific system prompts

Intent priority: `recruitment` > `resume` > `interview` > `learning` > `career` > `business` > `general`

> **Note:** The current architecture is an orchestrated specialized-agent system. Agents do not autonomously plan or delegate to each other. The orchestrator is the single routing authority.

---

## Generative AI

The project uses a **pretrained Qwen2.5 3B model** running locally through Ollama. No model training or fine-tuning has been performed for this project.

| Aspect | Implementation |
|--------|---------------|
| **Model** | Qwen2.5 3B (3 billion parameters) |
| **Runtime** | Ollama (local inference server) |
| **Inference** | Local CPU/GPU via Ollama API |
| **Prompting** | Domain-specific system prompts per agent and interview phase |
| **Context** | Bounded conversation history (last 6 messages, 400 char truncation) |
| **Streaming** | NDJSON streaming via Ollama `/api/generate` with `stream=true` |
| **Fallback** | Heuristic code-based responses when LLM is unavailable |

The application relies on application-level prompting and workflow orchestration rather than model-level customization.

---

## AI Interview System

The interview system is the most complex subsystem, implementing a complete automated interview workflow with adaptive questioning and evaluation.

### Interview Workflow

```
Interview Setup (candidate info, JD, resume)
        |
        v
  Interview Plan  <----  LLM generates 7-10 topics
        |                (fallback: heuristic role mapping)
        v
  Question Generation  <----  Adaptive to role, resume, prior answers
        |                     (fallback: template-based questions)
        v
  Candidate Answer  <----  Voice (STT) or text input
        |
        v
  Answer Evaluation  <----  LLM multi-dimensional scoring
        |                   (fallback: keyword-based heuristic scoring)
        v
  Adaptive Next Question  <----  Difficulty adjusts to performance
        |                         Follow-up on weak areas
        v
  ... (repeat for configured question count)
        |
        v
  Final Report  <----  LLM-generated summary
                      (fallback: heuristic aggregation)
```

### Interview Components

| Component | File | Role |
|-----------|------|------|
| **Interview Engine** | `engine.py` | Plan generation, question generation, final report |
| **Evaluator** | `evaluator.py` | Answer scoring across technical, communication, depth, clarity |
| **LLM Helpers** | `llm_helpers.py` | JSON extraction, output normalization, validation |
| **Prompts** | `prompts.py` | System prompts for each interview phase |
| **Models** | `models.py` | Pydantic request/response schemas with validators |
| **Service** | `service.py` | SQLite-backed interview CRUD and window management |
| **Session Service** | `session_service.py` | SQLite-backed session state, question/answer persistence |
| **Routes** | `routes.py` | Interview scheduling API endpoints |
| **Session Routes** | `session_routes.py` | Live session API endpoints |

### Evaluation Dimensions

Each answer is evaluated on:
- **Technical Accuracy** (0-10)
- **Relevance** (0-10)
- **Depth** (0-10)
- **Clarity** (0-10)
- **Follow-up Needed** (boolean)
- **Difficulty Adjustment** (increase/decrease/maintain)

### Adaptive Behavior

- If the candidate scores strongly, difficulty increases for the next question
- If the candidate scores weakly, difficulty decreases
- If `follow_up_needed` is flagged, the next question stays on the same topic
- Questions are distributed proportionally across the interview plan topics

### Heuristic Fallbacks

Every LLM call has a code-based fallback ensuring graceful degradation:

| Phase | Fallback Strategy |
|-------|-------------------|
| Plan Generation | Role-keyword mapping (Data Analyst, Backend, HR, Frontend, AI/ML, Generic) |
| Question Generation | Template-based questions per topic with resume awareness |
| Answer Evaluation | Keyword density, word count, example detection, metrics detection |
| Final Report | Score aggregation, dimension-based strength/weakness derivation |

---

## Voice Interview & Proctoring

### Voice Interaction

The interview session uses browser-native Web APIs for voice interaction:

| Capability | API | Implementation |
|------------|-----|----------------|
| **Speech-to-Text** | Web Speech Recognition API | Continuous recognition with interim results, auto-restart on pause |
| **Text-to-Speech** | Speech Synthesis API | AI reads questions aloud, replays on demand |
| **Graceful Degradation** | Feature detection | Falls back to text input/output when voice APIs are unavailable |

Voice features include:
- Live transcript display during recording
- Editable transcript review before submission
- Intro speech before first question ("Hello, [name]. Welcome to your AI interview...")
- Replay button for re-listening to questions

### Browser-Level Proctoring

The proctoring system monitors interview integrity through browser events:

| Event | Severity | Description |
|-------|----------|-------------|
| `tab_hidden` | Warning | Candidate switched tabs |
| `tab_visible` | Info | Candidate returned to tab |
| `fullscreen_entered` | Info | Fullscreen mode activated |
| `fullscreen_exited` | Warning | Fullscreen mode exited |
| `camera_permission_denied` | Warning | Camera access denied |
| `microphone_permission_denied` | Warning | Microphone access denied |
| `camera_stream_interrupted` | Warning | Camera track ended or muted |
| `microphone_stream_interrupted` | Warning | Microphone track ended or muted |
| `speech_recognition_error` | Warning | Speech recognition API error |

> **Note:** This is basic browser-level proctoring using DOM and MediaStream APIs. It is not an advanced computer-vision proctoring platform.

---

## Conversation Memory

| Aspect | Implementation |
|--------|---------------|
| **Storage** | In-memory Python dictionary (process-scoped) |
| **Key** | `conversation_id` (UUID or client-provided) |
| **Capacity** | Maximum 10 turns (20 messages: 10 user + 10 assistant) |
| **Context Window** | Last 6 messages used for LLM context |
| **Truncation** | Messages truncated to 400 characters |
| **Persistence** | Not implemented -- resets on server restart |

The `conversation_id` is generated server-side and returned to the client, which stores it in `localStorage` for session continuity.

---

## Performance & Reliability

| Mechanism | Implementation |
|-----------|---------------|
| **Streaming** | NDJSON streaming for real-time token delivery |
| **Bounded Context** | Conversation history capped at 10 turns to control prompt size |
| **LLM Timeouts** | 8-second timeout for non-streaming requests |
| **Heuristic Fallbacks** | Code-based responses when Ollama is unavailable |
| **Malformed Response Handling** | Multi-layer JSON extraction with normalization |
| **Interview Fallbacks** | Every interview phase has a heuristic alternative |
| **Error Codes** | Structured OllamaError with specific HTTP status mapping |
| **Health Checks** | Ollama availability and model presence verified |

---

## Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **Frontend** | React | 19.2 |
| **Build Tool** | Vite | 8.2 |
| **Linter** | Oxlint | 1.79 |
| **Backend** | FastAPI | 0.115 |
| **Server** | Uvicorn | 0.30 |
| **HTTP Client** | httpx | 0.27 |
| **Validation** | Pydantic | 2.9 |
| **AI Model** | Qwen2.5 3B | -- |
| **Model Runtime** | Ollama | -- |
| **Database** | SQLite | (interview data) |
| **Testing** | pytest | -- |
| **Version Control** | Git | -- |

---

## Project Structure

```
Ardhanarishwar/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI entry point
│   │   ├── agents/                    # Specialized AI agents
│   │   │   ├── career_agent.py
│   │   │   ├── resume_agent.py
│   │   │   ├── interview_agent.py
│   │   │   ├── learning_agent.py
│   │   │   ├── recruitment_agent.py
│   │   │   └── business_agent.py
│   │   ├── interview/                 # Interview system
│   │   │   ├── engine.py
│   │   │   ├── evaluator.py
│   │   │   ├── llm_helpers.py
│   │   │   ├── models.py
│   │   │   ├── prompts.py
│   │   │   ├── routes.py
│   │   │   ├── service.py
│   │   │   ├── session_routes.py
│   │   │   └── session_service.py
│   │   └── services/                  # Core services
│   │       ├── conversation_memory.py
│   │       ├── llm.py
│   │       └── orchestrator.py
│   ├── tests/                         # Test suite
│   │   ├── test_conversation_memory.py
│   │   ├── test_interview.py
│   │   ├── test_orchestrator.py
│   │   ├── test_question_count.py
│   │   ├── test_report_feedback.py
│   │   └── test_session.py
│   ├── requirements.txt
│   └── .venv/
├── frontend/
│   ├── src/
│   │   ├── main.jsx                   # Entry point
│   │   ├── App.jsx                    # Root component + chat UI
│   │   ├── App.css                    # Dark theme styles
│   │   ├── api.js                     # Chat API service
│   │   ├── interviewApi.js            # Interview API service
│   │   ├── InterviewViews.jsx         # Scheduling & lobby UI
│   │   └── InterviewSession.jsx       # Live interview session
│   ├── public/
│   ├── package.json
│   ├── vite.config.js
│   └── .env.example
├── data/
│   └── interviews.db                  # SQLite interview database
├── docs/                              # Documentation
├── demo_video.mp4                     # Project demo video
├── interview_feedback.png             # Interview feedback screenshot
├── .env.example                       # Environment configuration template
├── .gitignore
└── README.md
```

---

## API Endpoints

### Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Service status |
| `GET` | `/api/health` | Health check |
| `POST` | `/api/chat` | Non-streaming chat |
| `POST` | `/api/chat/stream` | Streaming chat (NDJSON) |

### Interview Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/interviews` | Create interview |
| `GET` | `/api/interviews` | List all interviews |
| `GET` | `/api/interviews/{id}` | Get interview details |
| `POST` | `/api/interviews/{id}/start` | Start interview |
| `POST` | `/api/interviews/{id}/cancel` | Cancel interview |

### Interview Session

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/interviews/{id}/session/start` | Start AI session (generates plan + first question) |
| `GET` | `/api/interviews/{id}/session` | Get current session state |
| `POST` | `/api/interviews/{id}/session/answer` | Submit answer, receive next question or final report |
| `POST` | `/api/interviews/{id}/session/end` | End session early, generate final report |

---

## Testing & Verification

<p align="center">
  <img src="https://img.shields.io/badge/Backend_Tests-129%20passed-4CAF50?style=for-the-badge&logo=pytest&logoColor=white" alt="129 tests passed">
  <br><br>
  <img src="https://img.shields.io/badge/Frontend_Build-Successful-2196F3?style=for-the-badge&logo=vite&logoColor=white" alt="Frontend build successful">
</p>

**Test Coverage:**

| Test File | Focus Area |
|-----------|-----------|
| `test_orchestrator.py` | Intent detection, keyword routing |
| `test_conversation_memory.py` | Memory management, context building |
| `test_interview.py` | Interview models, CRUD, window logic, API |
| `test_session.py` | Session start/answer/end flow, completion |
| `test_question_count.py` | Question count validation, completion logic |
| `test_report_feedback.py` | Heuristic evaluator, report generation |

Run tests:
```bash
cd backend
python -m pytest tests/ -v
```

---

## Installation & Local Setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- [Ollama](https://ollama.ai) installed and running

### 1. Clone the repository

```bash
git clone https://github.com/princitripathi/Ardhanarishwar.git
cd Ardhanarishwar
```

### 2. Start Ollama and ensure the model is available

```bash
# Start Ollama (if not already running)
ollama serve

# Pull the required model
ollama pull qwen2.5:3b
```

### 3. Backend setup

```bash
cd backend

# Create virtual environment (if not already created)
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
# From project root
copy .env.example .env
# Linux/macOS:
# cp .env.example .env
```

Edit `.env` if needed. Default values work for local development:
- `OLLAMA_BASE_URL=http://localhost:11434`
- `OLLAMA_MODEL=qwen2.5:3b`

### 5. Start the backend

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend available at: `http://localhost:8000`

### 6. Frontend setup

```bash
cd frontend

# Install dependencies
npm install

# Configure environment
copy .env.example .env.local
# Linux/macOS:
# cp .env.example .env.local
```

### 7. Start the frontend

```bash
cd frontend
npm run dev
```

Frontend available at: `http://localhost:5173`

---

## Environment Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen2.5:3b` | Model identifier |
| `FRONTEND_URL` | `http://localhost:5173` | Frontend URL for CORS |
| `APP_ENV` | `development` | Application environment |
| `LOG_LEVEL` | `INFO` | Logging level |

The `.env` file should remain local and must not be committed to version control.

---

## Current Limitations

The following limitations reflect the current scope of the prototype:

| Limitation | Current State |
|-----------|---------------|
| **LLM Latency** | Local inference can have higher latency depending on hardware |
| **Conversation Memory** | In-memory only; resets on server restart |
| **Knowledge Base** | No RAG or document retrieval implemented |
| **Authentication** | No production auth/authorization system |
| **Proctoring** | Browser-level only; not computer-vision based |
| **LLM Dependency** | Requires local Ollama instance running |
| **Deployment** | Single-machine development architecture |
| **Intent Detection** | Keyword-based; may miss nuanced or complex requests |
| **Streaming Agents** | Streaming endpoint bypasses agent modules, using prompts directly |

---

## Future Development

Features planned but **not yet implemented**:

| Area | Planned Feature |
|------|----------------|
| **Knowledge Base** | RAG pipeline with document ingestion and vector search |
| **Memory** | Persistent PostgreSQL-backed conversation history |
| **Vector Store** | Embedding-based semantic search infrastructure |
| **Agent Autonomy** | Advanced agent-to-agent delegation and planning workflows |
| **Authentication** | Production user auth, RBAC, and session management |
| **Proctoring** | Computer-vision based eye-tracking and environment analysis |
| **Inference** | Dedicated GPU inference infrastructure |
| **Deployment** | Containerized cloud deployment with auto-scaling |
| **Analytics** | Admin dashboard with interview and usage analytics |
| **Integrations** | Enterprise HR system connectors (ATS, HRIS) |
| **Model** | Domain-specific fine-tuning if sufficient training data becomes available |

---

## Scalability Vision

```
                          FUTURE / PRODUCTION ARCHITECTURE

 Users
   |
   v
 Load Balancer
   |
   v
 API Servers (horizontal scaling)
   |
   v
 Orchestrator  +  Auth / RBAC
   |
   +--------+--------+--------+
   |        |        |        |
   v        v        v        v
Agents   RAG      Interview  Analytics
         Service   Service    Service
   |        |        |        |
   +--------+--------+--------+
   |
   v
 LLM Inference Infrastructure
 (GPU cluster / managed inference)
   |
   v
 PostgreSQL  +  Vector Database  +  Redis Cache
```

---

## Why This Project?

Ardhanarishwar demonstrates several technically interesting patterns:

- **Multi-workflow AI platform** -- Combines career, resume, interview, learning, recruitment, and business assistance in one application
- **Local LLM integration** -- Runs entirely on local infrastructure using Ollama, with no external API keys required
- **Modular agent architecture** -- Domain-specialized agents with a centralized orchestrator for clean separation of concerns
- **Adaptive interview system** -- Dynamic question generation, multi-dimensional evaluation, and difficulty adjustment based on candidate performance
- **Voice interaction** -- Browser-native speech recognition and synthesis for hands-free interview participation
- **Graceful degradation** -- Heuristic fallbacks at every LLM touchpoint ensure the system remains functional even when the model is unavailable
- **Extensible design** -- Clear boundaries between agents, services, and interview components allow for independent extension

---

## Security Notes

| Measure | Status |
|---------|--------|
| `.env` in `.gitignore` | Implemented |
| Secrets not committed | Implemented |
| Environment-based configuration | Implemented |
| CORS origin restriction | Implemented (`localhost:5173`) |
| Input validation (Pydantic) | Implemented |
| Production auth/RBAC | Not implemented |
| Rate limiting | Not implemented |
| HTTPS enforcement | Not implemented |

---

## Documentation

The `docs/` directory is currently empty. Documentation is maintained in this README.

---

## Author

**Princi Tripathi**

[github.com/princitripathi](https://github.com/princitripathi)
