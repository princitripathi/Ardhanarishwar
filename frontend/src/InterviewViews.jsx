import { useState, useEffect } from 'react'
import { createInterview, getInterview, listInterviews, startInterview, cancelInterview, uploadResumeFile, startSession, getSession } from './interviewApi'

function formatDate(dateStr) {
  try {
    const d = new Date(dateStr + 'T00:00:00')
    return d.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
  } catch { return dateStr }
}
function formatTime(timeStr) {
  try {
    const [h, m] = timeStr.split(':').map(Number)
    const d = new Date()
    d.setHours(h, m)
    return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })
  } catch { return timeStr }
}

export function InterviewEntryCard({ onSchedule }) {
  return (
    <div className="interview-entry-card">
      <div className="interview-entry-icon">◎</div>
      <div className="interview-entry-text">
        <h3>AI Interview</h3>
        <p>Conduct a scheduled AI interview based on JD + Resume</p>
      </div>
      <button className="interview-entry-btn" onClick={onSchedule}>Schedule Interview</button>
    </div>
  )
}

export function InterviewSchedule({ onScheduled, onCancelView }) {
  const [form, setForm] = useState({
    candidate_name: '',
    candidate_email: '',
    job_title: '',
    job_description: '',
    resume_text: '',
    scheduled_date: '',
    scheduled_time: '',
    duration_minutes: 20,
  })
  const [fileName, setFileName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [uploading, setUploading] = useState(false)

  const handleChange = (e) => {
    const { name, value } = e.target
    setForm((f) => ({ ...f, [name]: value }))
  }

  const handleFile = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setFileName(file.name)
    setUploading(true)
    setError(null)
    try {
      const text = await uploadResumeFile(file)
      if (text && text.trim().length > 10) {
        setForm((f) => ({ ...f, resume_text: text }))
      } else {
        setError('Could not extract text from file. Please paste resume text manually.')
      }
    } catch (err) {
      setError(err.message || 'Failed to read file')
    } finally {
      setUploading(false)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    if (!form.candidate_name.trim()) return setError('Candidate name is required')
    if (!form.job_title.trim()) return setError('Job title is required')
    if (!form.job_description.trim()) return setError('Job description is required')
    if (!form.resume_text.trim()) return setError('Resume is required')
    if (!form.scheduled_date) return setError('Scheduled date is required')
    if (!form.scheduled_time) return setError('Scheduled time is required')
    const dur = Number(form.duration_minutes)
    if (!dur || dur < 5 || dur > 120) return setError('Duration must be 5-120 minutes')

    setLoading(true)
    try {
      const res = await createInterview({
        candidate_name: form.candidate_name.trim(),
        candidate_email: form.candidate_email.trim() || null,
        job_title: form.job_title.trim(),
        job_description: form.job_description.trim(),
        resume_text: form.resume_text.trim(),
        scheduled_date: form.scheduled_date,
        scheduled_time: form.scheduled_time,
        duration_minutes: dur,
      })
      onScheduled(res.interview_id)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="interview-schedule">
      <div className="interview-schedule-header">
        <h2>Schedule AI Interview</h2>
        <p>Create a scheduled interview based on JD and Resume</p>
      </div>
      <form onSubmit={handleSubmit} className="interview-form">
        <div className="form-row">
          <label>Candidate Name *</label>
          <input name="candidate_name" value={form.candidate_name} onChange={handleChange} placeholder="John Doe" />
        </div>
        <div className="form-row">
          <label>Candidate Email</label>
          <input name="candidate_email" type="email" value={form.candidate_email} onChange={handleChange} placeholder="john@example.com" />
        </div>
        <div className="form-row">
          <label>Job Title *</label>
          <input name="job_title" value={form.job_title} onChange={handleChange} placeholder="AI/ML Engineer" />
        </div>
        <div className="form-row">
          <label>Job Description *</label>
          <textarea name="job_description" value={form.job_description} onChange={handleChange} placeholder="Paste job description..." rows={4} />
        </div>
        <div className="form-row">
          <label>Resume *</label>
          <div className="resume-upload-row">
            <label className="file-btn">
              {uploading ? 'Reading...' : fileName ? fileName : 'Choose file'}
              <input type="file" accept=".txt,.pdf,.doc,.docx" onChange={handleFile} hidden />
            </label>
            <span className="file-hint">or paste below (reuses existing upload if available)</span>
          </div>
          <textarea name="resume_text" value={form.resume_text} onChange={handleChange} placeholder="Paste resume text..." rows={6} />
        </div>
        <div className="form-grid-3">
          <div className="form-row">
            <label>Scheduled Date *</label>
            <input name="scheduled_date" type="date" value={form.scheduled_date} onChange={handleChange} />
          </div>
          <div className="form-row">
            <label>Scheduled Time *</label>
            <input name="scheduled_time" type="time" value={form.scheduled_time} onChange={handleChange} />
          </div>
          <div className="form-row">
            <label>Duration (min) *</label>
            <input name="duration_minutes" type="number" min={5} max={120} value={form.duration_minutes} onChange={handleChange} />
          </div>
        </div>
        {error && <div className="error-banner">{error}</div>}
        <div className="form-actions">
          <button type="button" className="btn-secondary" onClick={onCancelView} disabled={loading}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={loading || uploading}>{loading ? 'Scheduling...' : 'Schedule Interview'}</button>
        </div>
      </form>
    </div>
  )
}

export function InterviewScheduledCard({ interviewId, onView }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  useEffect(() => {
    let mounted = true
    getInterview(interviewId).then(d => { if (mounted) { setData(d); setLoading(false) } }).catch(e => { if (mounted) { setError(e.message); setLoading(false) } })
    return () => { mounted = false }
  }, [interviewId])
  if (loading) return <div className="interview-card loading">Loading...</div>
  if (error) return <div className="error-banner">{error}</div>
  if (!data) return null
  return (
    <div className="interview-card scheduled-card">
      <div className="interview-card-head">
        <span className="interview-badge">AI Interview Scheduled</span>
        <span className={`status-pill ${data.status}`}>{data.status}</span>
      </div>
      <div className="interview-card-body">
        <div className="kv"><span>Candidate:</span><strong>{data.candidate_name}</strong></div>
        <div className="kv"><span>Position:</span><strong>{data.job_title}</strong></div>
        <div className="kv"><span>Scheduled:</span><strong>{formatDate(data.scheduled_date)} {formatTime(data.scheduled_time)}</strong></div>
        <div className="kv"><span>Duration:</span><strong>{data.duration_minutes} minutes</strong></div>
        <div className="kv"><span>Status:</span><strong className="cap">{data.status}</strong></div>
      </div>
      <button className="btn-primary" onClick={() => onView(data.interview_id)}>View Interview</button>
    </div>
  )
}

export function InterviewLobby({ interviewId, onBack, onStartSession }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [starting, setStarting] = useState(false)
  const [message, setMessage] = useState(null)
  const [nowTick, setNowTick] = useState(Date.now())
  const [hasSession, setHasSession] = useState(false)
  const [totalQuestions, setTotalQuestions] = useState(10)
  const [countdown, setCountdown] = useState(null)

  const fetchData = async () => {
    try {
      const d = await getInterview(interviewId)
      setData(d)
      setError(null)
      // check if AI session already exists
      try {
        const s = await getSession(interviewId)
        if (s && s.status === 'active') setHasSession(true)
        else if (s && s.status === 'completed') setHasSession(true)
        else setHasSession(false)
      } catch (_) { setHasSession(false) }
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }
  useEffect(() => { fetchData() }, [interviewId])
  useEffect(() => {
    const id = setInterval(() => setNowTick(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  // Re-fetch window every 30s to update can_join (backend authoritative)
  useEffect(() => {
    if (!data) return
    const id = setInterval(fetchData, 30000)
    return () => clearInterval(id)
  }, [data?.interview_id])
  // Countdown for not_started (UI only)
  useEffect(() => {
    if (!data?.window?.window_start || data.window.status !== 'not_started') {
      setCountdown(null)
      return
    }
    const tick = () => {
      const ws = new Date(data.window.window_start).getTime()
      const diff = ws - Date.now()
      if (diff <= 0) {
        setCountdown('00:00:00')
        fetchData()
        return
      }
      const h = Math.floor(diff / 3600000)
      const m = Math.floor((diff % 3600000) / 60000)
      const s = Math.floor((diff % 60000) / 1000)
      setCountdown(`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`)
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [data?.window?.window_start, data?.window?.status])

  const handleJoin = async () => {
    setStarting(true)
    setMessage(null)
    // Persist selected count for InterviewSession fallback (fixes hardcoded 10 bug)
    try { localStorage.setItem(`interview_${interviewId}_total`, String(totalQuestions)) } catch {}
    try {
      // Prefer AI interview session (Phase 2). Fallback to legacy start if needed.
      try {
        const sess = await startSession(interviewId, totalQuestions)
        setMessage({ type: 'success', text: 'AI interview session started.' })
        setData(prev => prev ? { ...prev, status: 'active' } : prev)
        setHasSession(true)
        try { localStorage.setItem(`interview_${interviewId}_total`, String(sess.total_questions || totalQuestions)) } catch {}
        if (onStartSession) {
          onStartSession(interviewId)
          return
        }
      } catch (sessionErr) {
        // If session already active, go to session view directly
        if (sessionErr.message && sessionErr.message.toLowerCase().includes('already active')) {
          if (onStartSession) { onStartSession(interviewId); return }
          setHasSession(true)
          setMessage({ type: 'success', text: 'Interview session already active.' })
          return
        }
        // Fallback: try legacy interview start for window validation message
        if (sessionErr.message && (sessionErr.message.includes('not started') || sessionErr.message.includes('window has ended') || sessionErr.message.includes('cancelled') || sessionErr.message.includes('completed'))) {
          throw sessionErr
        }
        // Otherwise try legacy
        const res = await startInterview(interviewId)
        setMessage({ type: 'success', text: res.message || 'Interview session started.' })
        setData(prev => prev ? { ...prev, status: res.status } : prev)
        // After legacy start, try to create AI session
        try {
          await startSession(interviewId, totalQuestions)
          if (onStartSession) onStartSession(interviewId)
        } catch (_) {}
      }
    } catch (e) {
      setMessage({ type: 'error', text: e.message })
    } finally { setStarting(false) }
  }

  const handleCancel = async () => {
    if (!confirm('Cancel this interview?')) return
    try {
      await cancelInterview(interviewId)
      fetchData()
    } catch (e) { setError(e.message) }
  }

  if (loading) return <div className="interview-lobby loading">Loading interview...</div>
  if (error) return <div className="error-banner">{error}<button className="btn-secondary" onClick={onBack} style={{marginLeft:12}}>Back</button></div>
  if (!data) return null

  const win = data.window
  const canJoin = win?.can_join && data.status === 'scheduled'
  const isActive = data.status === 'active'
  const isCancelled = data.status === 'cancelled'
  const isCompleted = data.status === 'completed'

  let joinMessage = win?.message || ''
  let windowState = win?.status || 'unknown'
  if (isCancelled) { joinMessage = 'This interview has been cancelled.'; windowState = 'CANCELLED' }
  else if (isCompleted) { joinMessage = 'This interview has already been completed.'; windowState = 'COMPLETED' }
  else if (isActive) { joinMessage = 'Interview session started.'; windowState = 'ACTIVE' }
  else if (win?.status === 'not_started') windowState = 'NOT_STARTED'
  else if (win?.status === 'joinable' && canJoin) windowState = 'JOINABLE'
  else if (win?.status === 'ended') { joinMessage = 'This interview window has ended.'; windowState = 'ENDED' }

  // Disable join unless canJoin (backend authoritative)
  const joinDisabled = !canJoin || starting || isCancelled || isCompleted

  void nowTick

  const isDev = import.meta.env.DEV
  const questionOptions = isDev
    ? [
        { value: 3, label: '3 questions', badge: 'Quick Test' },
        { value: 5, label: '5 questions', badge: null },
        { value: 10, label: '10 questions', badge: 'Recommended' },
        { value: 15, label: '15 questions', badge: null },
        { value: 20, label: '20 questions', badge: null },
      ]
    : [
        { value: 5, label: '5 questions', badge: null },
        { value: 10, label: '10 questions', badge: 'Recommended' },
        { value: 15, label: '15 questions', badge: null },
        { value: 20, label: '20 questions', badge: null },
      ]

  return (
    <div className="interview-lobby">
      <div className="lobby-header">
        <div className="lobby-brand">◈ ARDHANARISHWAR AI</div>
        <div className="lobby-title">AI INTERVIEW</div>
      </div>
      <div className="lobby-card">
        <div className="lobby-card-head">
          <span className="lobby-card-title">Scheduled Interview</span>
          <span className={`status-pill small ${data.status}`}>{windowState === 'JOINABLE' ? 'Joinable' : windowState === 'NOT_STARTED' ? 'Scheduled' : data.status}</span>
        </div>
        <div className="lobby-kv"><span>Role:</span><strong>{data.job_title}</strong></div>
        <div className="lobby-kv"><span>Candidate:</span><strong>{data.candidate_name}</strong></div>
        <div className="lobby-kv"><span>Scheduled:</span><strong>{formatDate(data.scheduled_date)} {formatTime(data.scheduled_time)}</strong></div>
        <div className="lobby-kv"><span>Duration:</span><strong>{data.duration_minutes} minutes</strong></div>
        <div className="lobby-kv"><span>Status:</span><span className={`status-pill small ${data.status}`}>{data.status}</span></div>
        <div className="lobby-scheduled-detail">
          <p>Your interview is scheduled for:</p>
          <strong>{formatDate(data.scheduled_date)} {formatTime(data.scheduled_time)}</strong>
          <span>You can join 5 minutes before the scheduled time.</span>
        </div>
        <div className="lobby-window-info">
          {isCancelled ? (
            <p>This interview has been cancelled.</p>
          ) : isCompleted ? (
            <p>This interview has already been completed.</p>
          ) : windowState === 'ENDED' ? (
            <p>This interview window has ended.</p>
          ) : windowState === 'JOINABLE' ? (
            <p>Your interview is now available. Click Join to start.</p>
          ) : windowState === 'NOT_STARTED' ? (
            <div className="countdown-block">
              <p>You can join 5 minutes before the scheduled time.</p>
              {countdown && (
                <div className="countdown">
                  <span className="countdown-label">Interview starts in</span>
                  <span className="countdown-time">{countdown}</span>
                </div>
              )}
            </div>
          ) : isActive ? (
            <p>Interview session started.</p>
          ) : (
            <p>{joinMessage}</p>
          )}
        </div>
        {!isCancelled && !isCompleted && data.status === 'scheduled' && (
          <div className="question-count-selector">
            <label className="selector-label">Number of questions</label>
            <div className="selector-options">
              {questionOptions.map(opt => (
                <button
                  key={opt.value}
                  type="button"
                  className={`selector-btn ${totalQuestions === opt.value ? 'active' : ''}`}
                  onClick={() => setTotalQuestions(opt.value)}
                  disabled={starting}
                  aria-pressed={totalQuestions === opt.value}
                >
                  <span className="selector-value">{opt.value}</span>
                  <span className="selector-text">{opt.label.replace(`${opt.value} `,'')}</span>
                  {opt.badge && <span className={`selector-badge ${opt.badge === 'Recommended' ? 'recommended' : 'quick'}`}>{opt.badge}</span>}
                </button>
              ))}
            </div>
            <p className="selector-hint">
              {totalQuestions === 3 ? 'Quick Test — 3 questions (development mode only)' : totalQuestions === 10 ? 'Recommended — 10 questions (default)' : `${totalQuestions} questions`}
            </p>
          </div>
        )}
        <button className="btn-primary lobby-join" onClick={handleJoin} disabled={joinDisabled}>
          {starting ? 'Starting...' : hasSession || isActive ? 'Enter Interview' : 'Join Interview'}
        </button>
        {(hasSession || isActive) && onStartSession && (
          <button className="btn-secondary" style={{width:'100%', marginTop:8}} onClick={()=>onStartSession(interviewId)}>Resume AI Interview →</button>
        )}
        {message && <div className={message.type === 'success' ? 'lobby-success' : 'error-banner'}>{message.text}</div>}
        <div className="lobby-actions">
          <button className="btn-secondary" onClick={onBack}>Back</button>
          {data.status === 'scheduled' && <button className="btn-danger" onClick={handleCancel}>Cancel Interview</button>}
        </div>
      </div>
      <div className="lobby-meta">
        <span>ID: {data.interview_id}</span>
        {win?.window_start && <span>Window: {new Date(win.window_start).toLocaleString()} — {win.window_end ? new Date(win.window_end).toLocaleString() : ''}</span>}
      </div>
    </div>
  )
}

export function InterviewList({ onSelect, onClose }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const fetchList = async () => {
    setLoading(true)
    try {
      const data = await listInterviews()
      setItems(data)
      setError(null)
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }
  useEffect(() => { fetchList() }, [])
  return (
    <div className="interview-list">
      <div className="interview-list-header">
        <h3>Scheduled Interviews</h3>
        <button className="btn-secondary small" onClick={fetchList}>Refresh</button>
        {onClose && <button className="btn-secondary small" onClick={onClose}>Close</button>}
      </div>
      {loading && <div>Loading...</div>}
      {error && <div className="error-banner">{error}</div>}
      {!loading && items.length === 0 && <div className="empty">No interviews scheduled yet.</div>}
      <div className="interview-list-grid">
        {items.map(it => (
          <div key={it.interview_id} className="interview-list-card" onClick={() => onSelect?.(it.interview_id)}>
            <div className="list-card-head">
              <strong>{it.candidate_name}</strong>
              <span className={`status-pill small ${it.status}`}>{it.status}</span>
            </div>
            <div className="list-card-sub">{it.job_title}</div>
            <div className="list-card-meta">{formatDate(it.scheduled_date)} {formatTime(it.scheduled_time)} • {it.duration_minutes}m</div>
            <div className="list-card-id">{it.interview_id}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
