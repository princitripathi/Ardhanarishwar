import json, httpx
resp = httpx.post("http://localhost:8001/api/chat", json={
    "message": "What is AI",
    "conversation_id": "test-done-reason"
}, timeout=60)
data = resp.json()
print(f"done_reason: {data.get('done_reason')}")
print(f"response_length: {len(data.get('response',''))}")
print(f"response ends with complete sentence: {data.get('response','').rstrip()[-1] in '.!?'}")
