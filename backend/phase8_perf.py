"""Phase 8 performance measurement - before/after.
Measures:
- routing latency
- retrieval latency
- memory latency
- validation latency
- health check latency
- model availability latency
- LLM generation latency (non-stream)
- TTFT streaming
- total orchestrator latency (mock vs live)
"""
import asyncio
import time
import statistics
import json
import os
from typing import Dict, List

# Setup to allow imports
# Run from backend folder: python phase8_perf.py

def p50(vals):
    if not vals:
        return None
    return statistics.median(vals)

def mean(vals):
    return statistics.mean(vals) if vals else None

def p95(vals):
    if not vals:
        return None
    s=sorted(vals)
    idx=int(len(s)*0.95)
    idx=min(idx, len(s)-1)
    return s[idx]

async def measure_routing():
    from app.services.orchestrator import detect_intent, analyze_intents, score_intents
    cases = [
        "Help me plan my career growth",
        "How can I improve my resume",
        "Prepare for interview",
        "I want to learn Generative AI",
        "We need to hire Python developers",
        "How to improve workforce productivity",
        "Hello, how are you?",
        "What is our company leave policy with reimbursement and etc with long query to test tokenization and routing overhead for performance measurement",
    ]
    latencies=[]
    for _ in range(5):
        for msg in cases:
            t0=time.perf_counter()
            detect_intent(msg)
            t1=time.perf_counter()
            latencies.append((t1-t0)*1000)
    return {"count": len(latencies), "mean": mean(latencies), "median": p50(latencies), "p95": p95(latencies), "min": min(latencies), "max": max(latencies)}

async def measure_retrieval():
    from app.rag.store import get_store
    from app.rag.retrieval import retrieve, format_context
    store=get_store()
    store.clear()
    # ingest 5 docs with realistic size
    for i in range(5):
        store.add_document("SampleCorp leave policy: 24 days paid annual leave. Remote work 2 days per week. Benefits include health insurance and 401k. " * 5, title=f"doc{i}", source=f"src{i}")
    queries=[
        "What is leave policy?",
        "Hello how are you?",
        "Explain generative AI roadmap",
        "Python developer resume help",
        "Company policy for remote work and annual leave and benefits",
    ]
    lats=[]
    for _ in range(5):
        for q in queries:
            t0=time.perf_counter()
            r=retrieve(q, top_k=3, threshold=0.12)
            ctx=format_context(r)
            t1=time.perf_counter()
            lats.append((t1-t0)*1000)
    return {"count": len(lats), "mean": mean(lats), "median": p50(lats), "p95": p95(lats), "min": min(lats), "max": max(lats), "chunks": store.chunk_count()}

async def measure_memory():
    from app.services import user_memory as mem
    from app.services import conversation_memory as cm
    mem.clear_all()
    cm.clear_all()
    # setup profile
    mem.upsert_profile("perf-user", {"preferred_name": "Priya", "career_goal": "Generative AI Developer", "known_skills": ["Python", "ML"], "learning_interests": ["MLOps"]})
    lats_build=[]
    lats_extract=[]
    lats_update=[]
    msgs=["I want to become a Generative AI Developer", "Hello how are you?", "My name is Priya", "I know Python and Java"]
    for _ in range(10):
        for m in msgs:
            t0=time.perf_counter()
            mem.extract_memory_updates(m)
            lats_extract.append((time.perf_counter()-t0)*1000)
            t0=time.perf_counter()
            mem.build_memory_context("perf-user")
            lats_build.append((time.perf_counter()-t0)*1000)
            t0=time.perf_counter()
            mem.maybe_update_from_message("perf-user", m)
            lats_update.append((time.perf_counter()-t0)*1000)
    # also conversation memory
    cm_lat=[]
    for _ in range(20):
        cid="perf-conv"
        cm.add_message(cid, "user", "Hello testing memory performance with some content to ensure truncation works correctly and bounded context building is efficient")
        cm.add_message(cid, "assistant", "Response content for testing "*5)
        t0=time.perf_counter()
        hist=cm.get_history(cid)
        ctx=cm.build_context(hist)
        cm_lat.append((time.perf_counter()-t0)*1000)
    return {
        "extract": {"mean": mean(lats_extract), "median": p50(lats_extract), "p95": p95(lats_extract)},
        "build_context": {"mean": mean(lats_build), "median": p50(lats_build)},
        "maybe_update": {"mean": mean(lats_update), "median": p50(lats_update)},
        "conv_mem": {"mean": mean(cm_lat), "median": p50(cm_lat), "p95": p95(cm_lat)},
    }

async def measure_validation():
    from app.services.validation import validate_chat_response
    samples=[
        "Hello! This is a normal response with some content and bullet points: - point one - point two. This should be valid and pass quickly.",
        "I have access to live job listings and can fetch them for you right now with ATS score 87",
        "a "*500,
        "Mock response for career about Help me plan. Keywords: career growth plan. This is helpful answer with bullet points:\n- Point one\n- Point two",
    ]
    lats=[]
    for _ in range(30):
        for s in samples:
            t0=time.perf_counter()
            validate_chat_response(s, intent="career", rag_used=False, message="test")
            lats.append((time.perf_counter()-t0)*1000)
    return {"count": len(lats), "mean": mean(lats), "median": p50(lats), "p95": p95(lats), "max": max(lats)}

async def measure_health():
    from app.services.llm import check_ollama_health, is_model_available
    lats_health=[]
    lats_model=[]
    for _ in range(5):
        t0=time.perf_counter()
        await check_ollama_health()
        lats_health.append((time.perf_counter()-t0)*1000)
        t0=time.perf_counter()
        await is_model_available()
        lats_model.append((time.perf_counter()-t0)*1000)
    return {
        "health": {"mean": mean(lats_health), "median": p50(lats_health), "min": min(lats_health), "max": max(lats_health)},
        "model": {"mean": mean(lats_model), "median": p50(lats_model), "min": min(lats_model), "max": max(lats_model)},
        "combined": mean(lats_health) + mean(lats_model) if lats_health and lats_model else None,
    }

async def measure_llm_generation():
    from app.services.llm import generate_response
    msgs=["Hello, how are you? Be concise.", "Explain what is Python in 2 sentences."]
    lats=[]
    for msg in msgs:
        for _ in range(2):
            t0=time.perf_counter()
            try:
                r=await generate_response(msg, system_prompt="You are helpful. Be concise.")
                lats.append((time.perf_counter()-t0)*1000)
            except Exception as e:
                lats.append((time.perf_counter()-t0)*1000)
                print(f"LLM error {e}")
    return {"count": len(lats), "mean": mean(lats), "median": p50(lats), "p95": p95(lats), "min": min(lats) if lats else None, "max": max(lats) if lats else None}

async def measure_stream_ttft():
    from app.services.llm import generate_response_stream
    lats_ttft=[]
    lats_total=[]
    for _ in range(3):
        t0=time.perf_counter()
        ttft=None
        total_chars=0
        async for chunk in generate_response_stream("Hello, how are you? Be concise.", system_prompt="You are helpful. Be concise."):
            if ttft is None:
                ttft=(time.perf_counter()-t0)*1000
                lats_ttft.append(ttft)
            total_chars+=len(chunk)
        total=(time.perf_counter()-t0)*1000
        lats_total.append(total)
    return {"ttft": {"mean": mean(lats_ttft), "median": p50(lats_ttft), "min": min(lats_ttft) if lats_ttft else None, "max": max(lats_ttft) if lats_ttft else None},
            "total": {"mean": mean(lats_total), "median": p50(lats_total), "min": min(lats_total) if lats_total else None, "max": max(lats_total) if lats_total else None}}

async def measure_orchestrator_mock():
    from unittest.mock import AsyncMock, patch
    from app.services.orchestrator import route_message
    from app.services import conversation_memory as cm
    from app.services.orchestrator import _last_intent
    from app.services import user_memory as mem
    from app.rag.store import get_store
    # ensure clean
    cm.clear_all()
    _last_intent.clear()
    try: mem.clear_all()
    except: pass
    get_store().clear()
    get_store().add_document("SampleCorp policy: 24 days leave. "*10, title="policy", source="sample")
    cases=[
        "Hello, how are you?",
        "How can I improve my resume for a software engineer role?",
        "What is our company leave policy?",
        "I want to learn Generative AI, where to start?",
        "We need to hire 3 Python developers",
    ]
    lats=[]
    for msg in cases:
        mock_ret=type("obj",(),{"response": f"Mock response for {msg[:20]} with guidance. Keywords: helpful answer. - point one - point two. This is sufficiently long to pass completeness.", "model": "qwen2.5:3b"})()
        with patch("app.services.orchestrator.generate_response", new=AsyncMock(return_value=mock_ret)), \
             patch("app.agents.career_agent.generate_response", new=AsyncMock(return_value=mock_ret)), \
             patch("app.agents.resume_agent.generate_response", new=AsyncMock(return_value=mock_ret)), \
             patch("app.agents.interview_agent.generate_response", new=AsyncMock(return_value=mock_ret)), \
             patch("app.agents.learning_agent.generate_response", new=AsyncMock(return_value=mock_ret)), \
             patch("app.agents.recruitment_agent.generate_response", new=AsyncMock(return_value=mock_ret)), \
             patch("app.agents.business_agent.generate_response", new=AsyncMock(return_value=mock_ret)):
            for _ in range(3):
                cid=f"mock-perf-{msg[:10]}"
                t0=time.perf_counter()
                r=await route_message(msg, conversation_id=cid)
                lats.append((time.perf_counter()-t0)*1000)
    return {"count": len(lats), "mean": mean(lats), "median": p50(lats), "p95": p95(lats), "min": min(lats), "max": max(lats)}

async def measure_orchestrator_live():
    from app.services.orchestrator import route_message
    from app.services import conversation_memory as cm
    from app.services.orchestrator import _last_intent
    from app.services import user_memory as mem
    from app.rag.store import get_store
    cm.clear_all()
    _last_intent.clear()
    try: mem.clear_all()
    except: pass
    get_store().clear()
    get_store().add_document("SampleCorp policy: 24 days leave. "*10, title="policy", source="sample")
    cases=[
        "Hello, how are you?",
        "What is our company leave policy?",
    ]
    lats=[]
    for msg in cases:
        for _ in range(2):
            cid=f"live-perf-{msg[:10]}-{time.time()}"
            t0=time.perf_counter()
            try:
                r=await route_message(msg, conversation_id=cid)
                lats.append((time.perf_counter()-t0)*1000)
            except Exception as e:
                lats.append((time.perf_counter()-t0)*1000)
                print(f"live orchestrator error {e}")
    return {"count": len(lats), "mean": mean(lats), "median": p50(lats), "p95": p95(lats), "min": min(lats) if lats else None, "max": max(lats) if lats else None}

async def measure_orchestrator_stream_live():
    from app.services.orchestrator import stream_message
    from app.services import conversation_memory as cm
    from app.services.orchestrator import _last_intent
    cm.clear_all()
    _last_intent.clear()
    ttfts=[]
    totals=[]
    for _ in range(2):
        cid=f"stream-live-{time.time()}"
        t0=time.perf_counter()
        ttft=None
        async for event in stream_message("Hello, how are you? Be concise.", conversation_id=cid):
            if event["type"]=="chunk" and ttft is None:
                ttft=(time.perf_counter()-t0)*1000
                ttfts.append(ttft)
        total=(time.perf_counter()-t0)*1000
        totals.append(total)
    return {"ttft": {"mean": mean(ttfts), "median": p50(ttfts)}, "total": {"mean": mean(totals), "median": p50(totals)}}

async def main():
    report={}
    print("=== Phase 8 Perf Measurement ===")
    print("Measuring routing...")
    report["routing"] = await measure_routing()
    print(report["routing"])
    print("Measuring retrieval...")
    report["retrieval"] = await measure_retrieval()
    print(report["retrieval"])
    print("Measuring memory...")
    report["memory"] = await measure_memory()
    print(report["memory"])
    print("Measuring validation...")
    report["validation"] = await measure_validation()
    print(report["validation"])
    print("Measuring health checks...")
    report["health"] = await measure_health()
    print(report["health"])
    print("Measuring LLM generation (live)...")
    report["llm_generation"] = await measure_llm_generation()
    print(report["llm_generation"])
    print("Measuring stream TTFT...")
    report["stream"] = await measure_stream_ttft()
    print(report["stream"])
    print("Measuring orchestrator mock (no LLM)...")
    report["orchestrator_mock"] = await measure_orchestrator_mock()
    print(report["orchestrator_mock"])
    print("Measuring orchestrator live...")
    report["orchestrator_live"] = await measure_orchestrator_live()
    print(report["orchestrator_live"])
    print("Measuring orchestrator stream live...")
    report["orchestrator_stream_live"] = await measure_orchestrator_stream_live()
    print(report["orchestrator_stream_live"])
    # Save
    with open("phase8_perf_before.json" if not os.path.exists("phase8_perf_before.json") else "phase8_perf_after.json", "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    # summary
    print("\n=== SUMMARY ===")
    print(f"Routing median {report['routing']['median']:.2f}ms (should be <5ms)")
    print(f"Retrieval median {report['retrieval']['median']:.2f}ms")
    print(f"Health+Model combined {report['health']['combined']:.1f}ms (BOTTLENECK overhead)")
    print(f"LLM generation median {report['llm_generation']['median']:.1f}ms (MAIN BOTTLENECK)")
    print(f"Stream TTFT median {report['stream']['ttft']['median']:.1f}ms")
    print(f"Orchestrator mock median {report['orchestrator_mock']['median']:.1f}ms (non-LLM overhead)")
    print(f"Orchestrator live median {report['orchestrator_live']['median']:.1f}ms")
    print(f"Validation median {report['validation']['median']:.2f}ms")

if __name__=="__main__":
    asyncio.run(main())
