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

export async function sendChatMessageStream(message, { onMeta, onChunk, onDone, onError, conversationId } = {}) {
  const body = conversationId ? { message, conversation_id: conversationId } : { message };
  const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
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

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.trim()) continue;
      let event;
      try {
        event = JSON.parse(line);
      } catch {
        continue;
      }
      if (event.type === 'meta' && onMeta) onMeta(event);
      else if (event.type === 'chunk' && onChunk) onChunk(event.content);
      else if (event.type === 'error' && onError) onError(event.detail);
    }
  }
  if (buffer.trim()) {
    try {
      const event = JSON.parse(buffer);
      if (event.type === 'chunk' && onChunk) onChunk(event.content);
      else if (event.type === 'error' && onError) onError(event.detail);
    } catch {
      // ignore
    }
  }
  if (onDone) onDone();
}