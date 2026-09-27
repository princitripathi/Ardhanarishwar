import asyncio, httpx, json

async def test():
    async with httpx.AsyncClient(timeout=120) as c:
        # Test SSE streaming with done_reason
        print("=== Testing SSE done_reason flow ===")
        async with c.stream("POST", "http://localhost:8001/api/chat/stream",
            json={"message": "What is AI", "conversation_id": "test-done-reason"},
            headers={"Content-Type": "application/json"}
        ) as response:
            last_done_reason = None
            chunk_count = 0
            total_len = 0
            async for piece in response.aiter_bytes():
                text = piece.decode('utf-8', errors='replace')
                for event_str in text.strip().split('\n\n'):
                    if not event_str.strip(): continue
                    if not event_str.startswith('data: '): continue
                    data = event_str[6:]
                    try:
                        event = json.loads(data)
                    except: continue
                    if event.get('type') == 'chunk':
                        chunk_count += 1
                        total_len += len(event.get('content', ''))
                        if event.get('done_reason'):
                            last_done_reason = event.get('done_reason')
                        if event.get('done_reason') == 'stop' or event.get('done_reason') == 'length':
                            print(f"  Chunk {chunk_count}: content_len={len(event.get('content',''))}, done_reason={event.get('done_reason')}")
            print(f"  Total chunks: {chunk_count}, Total length: {total_len}, Last done_reason: {last_done_reason}")
            
            # Test non-streaming done_reason
            print("\n=== Testing non-streaming done_reason ===")
            resp = await c.post("http://localhost:8001/api/chat", json={
                "message": "What is AI",
                "conversation_id": "test-done-reason-2"
            })
            data = resp.json()
            print(f"  done_reason: {data.get('done_reason')}")
            print(f"  response_length: {len(data.get('response',''))}")

asyncio.run(test())
