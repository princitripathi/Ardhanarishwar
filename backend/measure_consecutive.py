"""Measure consecutive calls to show cache benefit in isolation."""
import asyncio, time
from app.services.llm import clear_health_cache
from app.services.orchestrator import route_message, stream_message
from app.services import conversation_memory as cm
from app.services.orchestrator import _last_intent
from app.services import user_memory as mem
from app.rag.store import get_store

async def consecutive_non_stream():
    clear_health_cache()
    cm.clear_all()
    _last_intent.clear()
    try: mem.clear_all()
    except: pass
    get_store().clear()
    get_store().add_document("SampleCorp policy: 24 days leave. " *5, title="policy", source="sample")
    print("=== Consecutive non-stream route_message (same query, cache warms after 1st) ===")
    for i in range(5):
        cid=f"consec-{i}-{time.time()}"
        t0=time.perf_counter()
        r=await route_message("Hello, how are you?", conversation_id=cid)
        elapsed=(time.perf_counter()-t0)*1000
        print(f"Call {i+1}: {elapsed:.1f}ms (health cache {'miss' if i==0 else 'hit'}) rag_used={r['rag_used']} len={len(r['response'])}")

async def consecutive_stream():
    clear_health_cache()
    cm.clear_all()
    _last_intent.clear()
    print("\n=== Consecutive stream TTFT ===")
    for i in range(3):
        cid=f"stream-consec-{i}-{time.time()}"
        t0=time.perf_counter()
        ttft=None
        total=0
        async for ev in stream_message("Hello, be concise.", conversation_id=cid):
            if ev["type"]=="chunk" and ttft is None:
                ttft=(time.perf_counter()-t0)*1000
        total=(time.perf_counter()-t0)*1000
        print(f"Stream {i+1}: TTFT {ttft:.1f}ms total {total:.1f}ms {'miss' if i==0 else 'hit'}")

asyncio.run(consecutive_non_stream())
asyncio.run(consecutive_stream())
