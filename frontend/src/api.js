const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export async function checkBackendHealth() {
  const response = await fetch(`${API_BASE_URL}/api/health`);
  if (!response.ok) {
    throw new Error('Backend unavailable');
  }
  return response.json();
}

export async function sendChatMessage(message, conversationId) {
  const body = conversationId ? { message, conversation_id: conversationId } : { message };
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || 'Failed to send message');
  }

  return response.json();
}

export async function sendChatMessageStream(message, { onMeta, onChunk, onDone, onError, conversationId, signal } = {}) {
  const body = conversationId ? { message, conversation_id: conversationId } : { message };
  const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || 'Failed to send message');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop() || '';
      for (const eventStr of events) {
        const lines = eventStr.trim().split('\n');
        let dataLine = null;
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            dataLine = line.slice(6);
            break;
          }
        }
        if (!dataLine) continue;
        let event;
        try { event = JSON.parse(dataLine); } catch { continue; }
        if (event.type === 'meta' && onMeta) await onMeta(event);
        else if (event.type === 'chunk' && onChunk) await onChunk(event.content, event.done_reason);
        else if (event.type === 'error' && onError) await onError(event.detail);
      }
    }
    if (buffer.trim()) {
      const lines = buffer.split('\n\n');
      for (const eventStr of lines) {
        const eventLines = eventStr.trim().split('\n');
        let dataLine = null;
        for (const line of eventLines) {
          if (line.startsWith('data: ')) { dataLine = line.slice(6); break; }
        }
        if (!dataLine) continue;
        let event;
        try { event = JSON.parse(dataLine); } catch { continue; }
        if (event.type === 'chunk' && onChunk) await onChunk(event.content, event.done_reason);
        else if (event.type === 'error' && onError) await onError(event.detail);
      }
    }
    if (onDone) onDone();
  } finally {
    try { reader.releaseLock() } catch {}
  }
}