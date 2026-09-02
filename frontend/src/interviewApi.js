const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export async function createInterview(payload) {
  const res = await fetch(`${API_BASE_URL}/api/interviews`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to create interview');
  return data;
}

export async function getInterview(id) {
  const res = await fetch(`${API_BASE_URL}/api/interviews/${id}`);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Interview not found');
  return data;
}

export async function listInterviews() {
  const res = await fetch(`${API_BASE_URL}/api/interviews`);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to list interviews');
  return data;
}

export async function startInterview(id) {
  const res = await fetch(`${API_BASE_URL}/api/interviews/${id}/start`, { method: 'POST' });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Cannot start interview');
  return data;
}

export async function cancelInterview(id) {
  const res = await fetch(`${API_BASE_URL}/api/interviews/${id}/cancel`, { method: 'POST' });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Cannot cancel interview');
  return data;
}

export async function startSession(interviewId, totalQuestions = 10) {
  const res = await fetch(`${API_BASE_URL}/api/interviews/${interviewId}/session/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ total_questions: totalQuestions }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to start session');
  return data;
}

export async function getSession(interviewId) {
  const res = await fetch(`${API_BASE_URL}/api/interviews/${interviewId}/session`);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Session not found');
  return data;
}

export async function submitAnswer(interviewId, sessionId, answer) {
  const res = await fetch(`${API_BASE_URL}/api/interviews/${interviewId}/session/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, answer }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to submit answer');
  return data;
}

export async function endSession(interviewId, sessionId) {
  const res = await fetch(`${API_BASE_URL}/api/interviews/${interviewId}/session/end`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Failed to end session');
  return data;
}

// Optional: try to reuse existing resume upload endpoint if available
export async function uploadResumeFile(file) {
  // Try existing endpoint POST /api/resume/upload
  const form = new FormData();
  form.append('file', file);
  try {
    const res = await fetch(`${API_BASE_URL}/api/resume/upload`, { method: 'POST', body: form });
    if (res.ok) {
      const data = await res.json().catch(() => ({}));
      // Try to extract text from response
      if (data.resume_text) return data.resume_text;
      if (data.text) return data.text;
      if (data.content) return data.content;
    }
  } catch (_) {
    // ignore, fallback to client-side reading
  }
  // Fallback: read as text client-side
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(new Error('Failed to read file'));
    reader.readAsText(file);
  });
}
