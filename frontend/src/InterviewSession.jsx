import { useState, useEffect, useRef } from 'react'
import { getInterview, startSession, submitAnswer, getSession, endSession } from './interviewApi'

function isSpeechRecognitionSupported() {
  return typeof window !== 'undefined' && ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)
}
function getSpeechRecognitionConstructor() {
  if (typeof window === 'undefined') return null
  return window.SpeechRecognition || window.webkitSpeechRecognition || null
}
function isSpeechSynthesisSupported() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

export function InterviewSession({ interviewId, sessionId: initialSessionId, onBack, onComplete }) {
  const [interview, setInterview] = useState(null)
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [finalReport, setFinalReport] = useState(null)

  // Voice / setup / proctoring state
  const [setupComplete, setSetupComplete] = useState(false)
  const [cameraStream, setCameraStream] = useState(null)
  const [micPermission, setMicPermission] = useState('prompt') // granted | denied | prompt | unsupported
  const [cameraPermission, setCameraPermission] = useState('prompt')
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [isListening, setIsListening] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const [proctorEvents, setProctorEvents] = useState([])
  const [proctorWarning, setProctorWarning] = useState(null)
  const [speechSupported] = useState(() => isSpeechRecognitionSupported())
  const [ttsSupported] = useState(() => isSpeechSynthesisSupported())
  const [setupError, setSetupError] = useState(null)
  const [introSpoken, setIntroSpoken] = useState(false)
  const [showQuestionText, setShowQuestionText] = useState(false)
  const [, setInterviewPhase] = useState('SETUP')
  const [timeRemaining, setTimeRemaining] = useState(null)
  const [sessionLoadingMessage, setSessionLoadingMessage] = useState('')

  const cameraVideoRef = useRef(null)
  const containerRef = useRef(null)
  const recognitionRef = useRef(null)
  const timerRef = useRef(null)
  const interviewTimerRef = useRef(null)
  const lastSpokenRef = useRef(null)
  const pendingSpeakRef = useRef(null)
  const baseTranscriptRef = useRef('')
  const listeningIntentRef = useRef(false)

  const warningsCount = proctorEvents.filter(e => e.severity === 'warning' || e.severity === 'critical').length

  function recordProctorEvent(type, severity = 'warning') {
    const ev = { type, timestamp: new Date().toISOString(), severity }
    setProctorEvents(prev => [...prev, ev])
    // Show warning for tab/fullscreen/mic/camera issues
    if (['tab_hidden', 'fullscreen_exited', 'camera_permission_denied', 'microphone_permission_denied', 'camera_stream_interrupted', 'microphone_stream_interrupted', 'speech_recognition_error'].includes(type)) {
      setProctorWarning('Please remain on the interview screen. This event has been recorded.')
      setTimeout(() => setProctorWarning(null), 4000)
    }
  }

  // Fetch interview info
  useEffect(() => {
    let mounted = true
    getInterview(interviewId).then(d => { if (mounted) setInterview(d) }).catch(e => { if (mounted) setError(e.message) })
    return () => { mounted = false }
  }, [interviewId])

  // Init session: fetch existing, do NOT auto-create before setup unless already exists
  useEffect(() => {
    let mounted = true
    async function init() {
      setLoading(true)
      setError(null)
      try {
        if (initialSessionId) {
          const s = await getSession(interviewId)
          if (mounted) {
            setSession(s)
            if (s.status === 'completed' && s.final_report) setFinalReport(s.final_report)
            // If session already exists and is active, we can consider setup needed still
          }
        } else {
          try {
            const existing = await getSession(interviewId)
            if (mounted) {
              setSession(existing)
              if (existing.status === 'completed' && existing.final_report) {
                setFinalReport(existing.final_report)
              }
            }
          } catch (_) {
            // No session yet – will be created after setup when user clicks Start Interview
            if (mounted) setSession(null)
          }
        }
      } catch (e) {
        if (mounted) setError(e.message)
      } finally {
        if (mounted) setLoading(false)
      }
    }
    init()
    return () => { mounted = false }
  }, [interviewId, initialSessionId])

  // Attach camera stream to video element - reliable lifecycle
  // Must re-attach whenever cameraStream changes OR the preview element mounts (setup -> interview transition)
  // Do NOT rely only on assigning srcObject during getUserMedia; video element may not have mounted yet.
  useEffect(() => {
    const video = cameraVideoRef.current
    if (video && cameraStream) {
      video.srcObject = cameraStream
      const p = video.play()
      if (p && typeof p.catch === 'function') p.catch(() => {})
    }
  }, [cameraStream, setupComplete])

  // Handle camera/mic track ended events
  useEffect(() => {
    if (!cameraStream) return
    const videoTracks = cameraStream.getVideoTracks()
    const audioTracks = cameraStream.getAudioTracks()
    const onVideoEnded = () => {
      recordProctorEvent('camera_stream_interrupted', 'warning')
      setCameraPermission('denied')
    }
    const onAudioEnded = () => {
      recordProctorEvent('microphone_stream_interrupted', 'warning')
      setMicPermission('denied')
    }
    videoTracks.forEach(t => { t.onended = onVideoEnded; t.onmute = onVideoEnded })
    audioTracks.forEach(t => { t.onended = onAudioEnded; t.onmute = onAudioEnded })
    return () => {
      videoTracks.forEach(t => { t.onended = null; t.onmute = null })
      audioTracks.forEach(t => { t.onended = null; t.onmute = null })
    }
  }, [cameraStream])

  // Proctoring: visibility and fullscreen listeners
  useEffect(() => {
    const onVisibility = () => {
      if (document.hidden) {
        recordProctorEvent('tab_hidden', 'warning')
      } else {
        recordProctorEvent('tab_visible', 'info')
      }
    }
    const onFullscreen = () => {
      const fs = !!document.fullscreenElement
      setIsFullscreen(fs)
      if (fs) recordProctorEvent('fullscreen_entered', 'info')
      else recordProctorEvent('fullscreen_exited', 'warning')
    }
    document.addEventListener('visibilitychange', onVisibility)
    document.addEventListener('fullscreenchange', onFullscreen)
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      document.removeEventListener('fullscreenchange', onFullscreen)
    }
  }, [])

  // SpeechRecognition setup - continuous with auto-restart to allow natural pauses
  useEffect(() => {
    if (!speechSupported) {
      setMicPermission(prev => prev === 'prompt' ? 'unsupported' : prev)
      return
    }
    const SR = getSpeechRecognitionConstructor()
    if (!SR) return
    const rec = new SR()
    rec.continuous = true
    rec.interimResults = true
    rec.lang = 'en-US'
    rec.onstart = () => {
      setIsListening(true)
      setElapsed(0)
      if (timerRef.current) clearInterval(timerRef.current)
      timerRef.current = setInterval(() => setElapsed(s => s + 1), 1000)
    }
    rec.onresult = (event) => {
      let text = ''
      for (let i = 0; i < event.results.length; i++) {
        text += event.results[i][0].transcript + ' '
      }
      text = text.trim()
      const base = baseTranscriptRef.current || ''
      const combined = base ? `${base} ${text}`.trim() : text
      setTranscript(combined)
    }
    rec.onend = () => {
      // Preserve transcript; auto-restart if user still intends to record (allows natural pauses)
      if (listeningIntentRef.current) {
        // Update base to current transcript before restart
        baseTranscriptRef.current = transcript
        try {
          // Small delay to avoid rapid restart loops
          setTimeout(() => {
            if (listeningIntentRef.current && recognitionRef.current) {
              try { recognitionRef.current.start() } catch {}
            }
          }, 250)
        } catch {}
        // Keep isListening true to keep UI in listening state
        return
      }
      setIsListening(false)
      if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
    }
    rec.onerror = (event) => {
      const err = event.error || 'unknown'
      recordProctorEvent('speech_recognition_error', 'warning')
      if (err === 'not-allowed' || err === 'permission-denied' || err === 'audio-capture') {
        listeningIntentRef.current = false
        setIsListening(false)
        if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
        setMicPermission('denied')
        recordProctorEvent('microphone_permission_denied', 'warning')
        setSetupError('Microphone permission denied. Please allow microphone access.')
      } else if (err === 'no-speech') {
        // No speech is natural pause - do not treat as end, auto-restart if intent active
        if (listeningIntentRef.current) {
          setTimeout(() => {
            if (listeningIntentRef.current && recognitionRef.current) {
              try { recognitionRef.current.start() } catch {}
            }
          }, 300)
          return
        }
        setIsListening(false)
        if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
      } else {
        // For other errors, try restart if intent active
        if (listeningIntentRef.current) {
          setTimeout(() => {
            if (listeningIntentRef.current && recognitionRef.current) {
              try { recognitionRef.current.start() } catch {}
            }
          }, 400)
          return
        }
        setIsListening(false)
        if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
        setSetupError(`Speech recognition error: ${err}`)
      }
    }
    rec.onaudiostart = () => setMicPermission('granted')
    recognitionRef.current = rec
    return () => {
      listeningIntentRef.current = false
      try { rec.abort() } catch {}
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [speechSupported])

  // Interview timer - visible countdown based on interview duration and session start
  useEffect(() => {
    if (!setupComplete || !interview || !session) return
    const duration = interview.duration_minutes || 20
    const startStr = session.started_at
    if (!startStr) return
    const startTime = new Date(startStr).getTime()
    if (isNaN(startTime)) return
    const durationMs = duration * 60 * 1000
    const update = () => {
      const now = Date.now()
      const elapsedMs = now - startTime
      const remainingMs = Math.max(0, durationMs - elapsedMs)
      setTimeRemaining(Math.floor(remainingMs / 1000))
      if (remainingMs <= 0) {
        if (interviewTimerRef.current) { clearInterval(interviewTimerRef.current); interviewTimerRef.current = null }
        // Auto end interview when time expires
        if (session.status === 'active' && !finalReport) {
          (async () => {
            try {
              listeningIntentRef.current = false
              if (isListening) {
                try { recognitionRef.current?.stop() } catch {}
              }
              if (ttsSupported) window.speechSynthesis.cancel()
              setSubmitting(true)
              const res = await endSession(interviewId, session.session_id)
              setFinalReport(res.final_report)
              setSession(prev => ({ ...prev, status: 'completed', final_report: res.final_report }))
              setInterviewPhase('COMPLETED')
            } catch {}
            finally { setSubmitting(false) }
          })()
        }
      }
    }
    update()
    if (interviewTimerRef.current) clearInterval(interviewTimerRef.current)
    interviewTimerRef.current = setInterval(update, 1000)
    return () => {
      if (interviewTimerRef.current) { clearInterval(interviewTimerRef.current); interviewTimerRef.current = null }
    }
  }, [setupComplete, interview, session?.started_at, session?.status])

  // TTS cleanup on unmount
  useEffect(() => {
    return () => {
      if (isSpeechSynthesisSupported()) window.speechSynthesis.cancel()
      if (timerRef.current) clearInterval(timerRef.current)
      if (interviewTimerRef.current) clearInterval(interviewTimerRef.current)
      if (cameraStream) cameraStream.getTracks().forEach(t => t.stop())
    }
  }, [cameraStream])

  // Auto speak question when it changes and setup complete (skip first question if intro will handle it)
  useEffect(() => {
    if (!setupComplete) return
    if (!introSpoken && (session?.question_number === 1)) return
    const text = session?.current_question || session?.questions_asked?.slice(-1)[0]?.question || ''
    if (!text || isSpeaking) return
    if (lastSpokenRef.current === text) return
    setInterviewPhase('AI_SPEAKING')
    if (!ttsSupported) {
      setShowQuestionText(true)
      return
    }
    setShowQuestionText(false)
    pendingSpeakRef.current = setTimeout(() => speakQuestion(text), 400)
    return () => clearTimeout(pendingSpeakRef.current)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.question_number, session?.current_question, setupComplete, introSpoken])

  function speakQuestion(text) {
    if (!text) return
    if (!ttsSupported) {
      setShowQuestionText(true)
      return
    }
    try {
      window.speechSynthesis.cancel()
      const utter = new SpeechSynthesisUtterance(text)
      utter.lang = 'en-US'
      utter.rate = 1
      utter.onstart = () => { setIsSpeaking(true); setShowQuestionText(true); setInterviewPhase('AI_SPEAKING') }
      utter.onend = () => { setIsSpeaking(false); setShowQuestionText(true); lastSpokenRef.current = text; setInterviewPhase('READY') }
      utter.onerror = () => { setIsSpeaking(false); setShowQuestionText(true); setInterviewPhase('READY') }
      window.speechSynthesis.speak(utter)
      lastSpokenRef.current = text
    } catch {
      setIsSpeaking(false)
      setShowQuestionText(true)
      setInterviewPhase('READY')
    }
  }
  function stopSpeaking() {
    if (ttsSupported) window.speechSynthesis.cancel()
    setIsSpeaking(false)
  }
  function handleReplay() {
    const text = session?.current_question || session?.questions_asked?.slice(-1)[0]?.question || ''
    if (text) {
      stopSpeaking()
      setTimeout(() => speakQuestion(text), 100)
    }
  }

  async function enableMedia() {
    setSetupError(null)
    // Check browser support
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setCameraPermission('unsupported')
      setMicPermission('unsupported')
      recordProctorEvent('camera_permission_denied', 'warning')
      recordProctorEvent('microphone_permission_denied', 'warning')
      setSetupError('Camera/Microphone not supported in this browser.')
      return
    }
    try {
      // Try combined first
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
      setCameraStream(stream)
      setCameraPermission('granted')
      setMicPermission('granted')
      return
    } catch (err) {
      // Fallback: try separately to give granular feedback
      let videoOk = false
      let audioOk = false
      try {
        const vs = await navigator.mediaDevices.getUserMedia({ video: true })
        // Keep video tracks, then try audio separately and merge
        setCameraStream(prev => {
          // Merge with existing if any
          const combined = new MediaStream([...vs.getVideoTracks()])
          // Try audio now
          return combined
        })
        videoOk = true
        setCameraPermission('granted')
        vs.getVideoTracks().forEach(t => {
          // will be merged later; keep stream
        })
        // Need to keep this stream temporarily
        if (!cameraStream) setCameraStream(vs)
        else {
          vs.getVideoTracks().forEach(t => cameraStream.addTrack(t))
        }
      } catch (e2) {
        setCameraPermission('denied')
        recordProctorEvent('camera_permission_denied', 'warning')
      }
      try {
        const as = await navigator.mediaDevices.getUserMedia({ audio: true })
        audioOk = true
        setMicPermission('granted')
        setCameraStream(prev => {
          if (!prev) return as
          as.getAudioTracks().forEach(t => prev.addTrack(t))
          return prev
        })
        if (!videoOk) {
          // Only audio stream exists
          setCameraStream(as)
        }
      } catch (e3) {
        setMicPermission('denied')
        recordProctorEvent('microphone_permission_denied', 'warning')
      }
      if (!videoOk && !audioOk) {
        setSetupError(`Permission denied: ${err.message || 'Please allow camera and microphone.'}`)
      } else if (!videoOk) {
        setSetupError('Camera denied. Proceeding with microphone only.')
      } else if (!audioOk) {
        setSetupError('Microphone denied. You can still type answers.')
      }
      // If at least one succeeded, keep stream
      // If both failed, error already set
    }
  }

  async function enterFullscreen() {
    try {
      const el = containerRef.current || document.documentElement
      if (el.requestFullscreen) await el.requestFullscreen()
      else if (el.webkitRequestFullscreen) await el.webkitRequestFullscreen()
      setIsFullscreen(true)
      recordProctorEvent('fullscreen_entered', 'info')
    } catch (e) {
      setSetupError('Fullscreen request was blocked. Please click Enter Fullscreen again after interaction.')
    }
  }
  async function exitFullscreen() {
    try {
      if (document.fullscreenElement && document.exitFullscreen) await document.exitFullscreen()
    } catch {}
  }

  function startListening() {
    if (isSpeaking) return
    if (!speechSupported || !recognitionRef.current) {
      setSetupError('Voice input not supported. Please type your answer.')
      return
    }
    setSetupError(null)
    baseTranscriptRef.current = transcript
    listeningIntentRef.current = true
    setIsListening(true)
    setElapsed(0)
    setInterviewPhase('LISTENING')
    try {
      recognitionRef.current.start()
    } catch (e) {
      try { recognitionRef.current.stop(); setTimeout(() => { baseTranscriptRef.current = transcript; listeningIntentRef.current = true; recognitionRef.current.start() }, 150) } catch {}
    }
  }
  function stopListening() {
    listeningIntentRef.current = false
    if (recognitionRef.current) {
      try { recognitionRef.current.stop() } catch {}
    }
    setIsListening(false)
    setInterviewPhase(transcript.trim() ? 'REVIEW' : 'READY')
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
  }

  async function ensureSession() {
    if (session && session.session_id) return session
    // Create new session after setup - respect lobby selection (fixes hardcoded 10 bug)
    let total = 10
    try {
      const stored = localStorage.getItem(`interview_${interviewId}_total`)
      if (stored) {
        const parsed = parseInt(stored, 10)
        if (parsed >= 3 && parsed <= 30) total = parsed
      }
    } catch {}
    // Also try to use session total if available via interview lobby state
    if (session && session.total_questions) total = session.total_questions
    try {
      const started = await startSession(interviewId, total)
      const newSess = {
        session_id: started.session_id,
        interview_id: interviewId,
        status: started.status,
        question_number: started.question_number,
        total_questions: started.total_questions,
        current_question: started.question,
        topic: started.topic,
        difficulty: started.difficulty,
        interview_plan: started.interview_plan,
      }
      setSession(newSess)
      return newSess
    } catch (e) {
      throw e
    }
  }

  function speakIntroductionThenQuestion(questionText) {
    if (questionText) setShowQuestionText(false)
    if (!ttsSupported) {
      if (questionText) setTimeout(() => speakQuestion(questionText), 200)
      else setShowQuestionText(true)
      setIntroSpoken(true)
      return
    }
    const name = interview?.candidate_name?.split(' ')[0] || 'there'
    const role = interview?.job_title || 'this position'
    const intro = `Hello, ${name}. Welcome to your AI interview for the ${role} position. I'll ask you a series of questions based on the role and your background. Please answer naturally and clearly. Let's begin.`
    setInterviewPhase('AI_SPEAKING')
    try {
      window.speechSynthesis.cancel()
      const utter = new SpeechSynthesisUtterance(intro)
      utter.lang = 'en-US'
      utter.rate = 1
      utter.onstart = () => setIsSpeaking(true)
      utter.onend = () => {
        setIsSpeaking(false)
        setIntroSpoken(true)
        if (questionText) setTimeout(() => speakQuestion(questionText), 500)
        else { setShowQuestionText(true); setInterviewPhase('READY') }
      }
      utter.onerror = () => {
        setIsSpeaking(false)
        setIntroSpoken(true)
        if (questionText) setTimeout(() => speakQuestion(questionText), 300)
        else { setShowQuestionText(true); setInterviewPhase('READY') }
      }
      window.speechSynthesis.speak(utter)
    } catch {
      setIsSpeaking(false)
      setIntroSpoken(true)
      if (questionText) setTimeout(() => speakQuestion(questionText), 300)
      else { setShowQuestionText(true); setInterviewPhase('READY') }
    }
  }

  async function handleStartInterview() {
    setSetupError(null)
    try {
      setError(null)
      if (!session || !session.session_id) {
        setLoading(true)
        setSessionLoadingMessage('Preparing interview...')
        setError(null)
        // Small delay to show preparing state before LLM call
        await new Promise(r => setTimeout(r, 200))
        setSessionLoadingMessage('Generating first question...')
        const s = await ensureSession()
        setSession(s)
        setSetupComplete(true)
        setInterviewPhase('AI_SPEAKING')
        setLoading(false)
        setSessionLoadingMessage('')
        const q = s.current_question || s.questions_asked?.slice(-1)?.[0]?.question || s.current_question
        if (q && ttsSupported) setShowQuestionText(false)
        else if (!ttsSupported && q) setShowQuestionText(true)
        else setShowQuestionText(false)
        // Speak intro then question
        setTimeout(() => speakIntroductionThenQuestion(q), 400)
      } else {
        setSetupComplete(true)
        const q = session.current_question || session.questions_asked?.slice(-1)[0]?.question
        // Only introduce on first question and not yet spoken
        if (session.question_number === 1 && !introSpoken) {
          if (q && ttsSupported) setShowQuestionText(false)
          setTimeout(() => speakIntroductionThenQuestion(q), 300)
        } else {
          if (q) {
            if (ttsSupported) setShowQuestionText(false)
            else setShowQuestionText(true)
            setTimeout(() => speakQuestion(q), 300)
          }
          setInterviewPhase('AI_SPEAKING')
        }
      }
    } catch (e) {
      setError(e.message)
      setLoading(false)
      setSessionLoadingMessage('')
      setInterviewPhase('ERROR')
    }
  }

  const handleSubmit = async (e) => {
    if (e) e.preventDefault()
    const text = transcript.trim()
    if (!text) {
      setError('Answer cannot be empty')
      return
    }
    if (!session?.session_id) {
      setError('Session not found')
      return
    }
    if (isListening) stopListening()
    if (isSpeaking) stopSpeaking()
    setSubmitting(true)
    setInterviewPhase('SUBMITTING')
    setError(null)
    try {
      const res = await submitAnswer(interviewId, session.session_id, text)
      if (res.status === 'completed') {
        setFinalReport(res.final_report)
        setSession(prev => ({ ...prev, status: 'completed', final_report: res.final_report }))
        setInterviewPhase('COMPLETED')
        // stop media
        if (cameraStream) cameraStream.getTracks().forEach(t => t.stop())
        if (document.fullscreenElement) { try { await document.exitFullscreen() } catch {} }
      } else {
        setSession(prev => ({
          ...prev,
          question_number: res.question_number,
          current_question: res.question,
          topic: res.topic,
          difficulty: res.difficulty,
          status: res.status,
        }))
        lastSpokenRef.current = null
        if (ttsSupported) setShowQuestionText(false)
        else setShowQuestionText(true)
        setInterviewPhase('AI_SPEAKING')
        // Auto speak next question via effect (will be triggered by question_number change)
      }
      setTranscript('')
      setElapsed(0)
      if (!isCompleted) setInterviewPhase('READY')
    } catch (err) {
      setError(err.message)
      setInterviewPhase('ERROR')
    } finally {
      setSubmitting(false)
    }
  }

  const handleEnd = async () => {
    if (!session?.session_id) return
    if (!confirm('End interview early?')) return
    if (isListening) stopListening()
    if (isSpeaking) stopSpeaking()
    setSubmitting(true)
    try {
      const res = await endSession(interviewId, session.session_id)
      setFinalReport(res.final_report)
      setSession(prev => ({ ...prev, status: 'completed' }))
      if (onComplete) onComplete(res.final_report)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <div className="interview-session loading">{sessionLoadingMessage || 'Loading interview session...'} {sessionLoadingMessage && <span className="dots"><i></i><i></i><i></i></span>}</div>
  if (error && !session && !setupComplete) return <div className="interview-session error"><div className="error-banner">{error}</div><button className="btn-secondary" onClick={onBack} style={{marginTop:12}}>Back</button></div>

  const isCompleted = session?.status === 'completed' || !!finalReport
  const qNum = session?.question_number || 1
  const total = session?.total_questions || 10
  const progress = Math.round((qNum / total) * 100)
  const questionText = session?.current_question || session?.questions_asked?.slice(-1)[0]?.question || (session ? '' : '')
  const topic = session?.topic || session?.current_topic || session?.questions_asked?.slice(-1)[0]?.topic || 'General'
  const difficulty = session?.difficulty || session?.questions_asked?.slice(-1)[0]?.difficulty || 'medium'

  const cameraActive = cameraStream && cameraStream.getVideoTracks().some(t => t.readyState === 'live' && t.enabled)
  const micActive = cameraStream ? cameraStream.getAudioTracks().some(t => t.readyState === 'live' && t.enabled) : false
  // Also consider listening as mic active for UI
  const micIndicatorActive = micActive || isListening

  if (isCompleted && finalReport) {
    // Stop streams
    if (cameraStream) cameraStream.getTracks().forEach(t => t.stop())
    if (isSpeaking) stopSpeaking()
    return (
      <div className="interview-session completed" ref={containerRef}>
        <div className="session-header">
          <div className="session-brand">◈ ARDHANARISHWAR AI</div>
          <div className="session-title">INTERVIEW COMPLETED</div>
          {interview && <div className="session-sub">{interview.job_title} • {interview.candidate_name}</div>}
        </div>
        <div className="report-card">
          <h3>Interview Report</h3>
          <div className="report-grid">
            <div className="report-score"><span>Overall</span><strong>{finalReport.overall_score}/10</strong></div>
            <div className="report-score"><span>Technical</span><strong>{finalReport.technical_score}/10</strong></div>
            <div className="report-score"><span>Communication</span><strong>{finalReport.communication_score}/10</strong></div>
            <div className="report-score"><span>Problem Solving</span><strong>{finalReport.problem_solving_score}/10</strong></div>
          </div>
          <div className="report-row">
            <span className={`rec-pill ${finalReport.recommendation?.toLowerCase().replace(/\s+/g,'-')}`}>{finalReport.recommendation}</span>
          </div>
          <p className="report-summary">{finalReport.summary}</p>
          {finalReport.strengths?.length > 0 && (
            <div className="report-section"><h4>Strengths</h4><ul>{finalReport.strengths.map((s,i)=><li key={i}>{s}</li>)}</ul></div>
          )}
          {finalReport.weaknesses?.length > 0 && (
            <div className="report-section"><h4>Areas for Improvement</h4><ul>{finalReport.weaknesses.map((s,i)=><li key={i}>{s}</li>)}</ul></div>
          )}
          {finalReport.topics_covered?.length > 0 && (
            <div className="report-section"><h4>Topics Covered</h4><div className="topics-tags">{finalReport.topics_covered.map((t,i)=><span key={i} className="topic-tag">{t}</span>)}</div></div>
          )}
          <div className="report-section"><h4>Proctoring Summary</h4><p className="report-summary">Events recorded: {proctorEvents.length} (Warnings: {warningsCount}) — camera and microphone used locally, no video stored in this phase.</p></div>
          <p className="report-disclaimer">AI recommendation is advisory only and not an objective hiring decision.</p>
          <div className="report-actions">
            <button className="btn-primary" onClick={onBack}>Back to Interviews</button>
          </div>
        </div>
      </div>
    )
  }

  if (!setupComplete) {
    const camStatus = cameraPermission === 'granted' && cameraActive ? 'granted' : cameraPermission === 'denied' ? 'denied' : cameraPermission === 'unsupported' ? 'unsupported' : 'prompt'
    const micStatus = micPermission === 'granted' && (micIndicatorActive || cameraStream) ? 'granted' : micPermission === 'denied' ? 'denied' : micPermission === 'unsupported' ? 'unsupported' : 'prompt'
    const canStartInterview = cameraPermission !== 'prompt' && micPermission !== 'prompt'
    const speakerReady = ttsSupported
    return (
      <div className="interview-session setup" ref={containerRef}>
        <div className="session-header">
          <div className="session-brand">◈ ARDHANARISHWAR AI</div>
          <div className="session-title">AI INTERVIEW SETUP</div>
          {interview && <div className="session-sub">{interview.job_title} • {interview.candidate_name}</div>}
        </div>
        <div className="setup-card">
          <h3>AI Interview Setup</h3>
          <p className="setup-desc">Before we begin, let's verify your interview environment.</p>
          <div className="setup-grid">
            <div className={`setup-item ${camStatus}`}>
              <div className="setup-item-head">
                <span className="setup-icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M14 12a2 2 0 11-4 0 2 2 0 014 0z"/><path d="M2 8h4l2-2h8l2 2h4v10a2 2 0 01-2 2H4a2 2 0 01-2-2V8z"/></svg></span>
                <span className="setup-label">Camera</span>
                <span className={`setup-badge ${camStatus}`}>{camStatus === 'granted' ? '✓ Detected' : camStatus === 'denied' ? '✗ Denied' : camStatus === 'unsupported' ? 'Unsupported' : '○ Not enabled'}</span>
              </div>
              <p className="setup-note">{camStatus === 'granted' ? 'Camera preview active' : camStatus === 'denied' ? 'Permission denied — please allow camera' : 'Click Enable to allow camera'}</p>
            </div>
            <div className={`setup-item ${micStatus}`}>
              <div className="setup-item-head">
                <span className="setup-icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 14a3 3 0 003-3V6a3 3 0 00-6 0v5a3 3 0 003 3z"/><path d="M19 10a7 7 0 01-14 0"/><line x1="12" y1="19" x2="12" y2="22"/><line x1="8" y1="22" x2="16" y2="22"/></svg></span>
                <span className="setup-label">Microphone</span>
                <span className={`setup-badge ${micStatus}`}>{micStatus === 'granted' ? '✓ Detected' : micStatus === 'denied' ? '✗ Denied' : micStatus === 'unsupported' ? 'Unsupported' : '○ Not enabled'}</span>
              </div>
              <p className="setup-note">{micStatus === 'granted' ? 'Microphone ready' : micStatus === 'denied' ? 'Permission denied — please allow microphone' : 'Click Enable to allow microphone'}</p>
            </div>
            <div className={`setup-item ${speechSupported ? 'granted' : 'denied'}`}>
              <div className="setup-item-head">
                <span className="setup-icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 3a3 3 0 00-3 3v6a3 3 0 006 0V6a3 3 0 00-3-3z"/><path d="M19 10a7 7 0 01-14 0"/><path d="M12 19v3"/></svg></span>
                <span className="setup-label">Voice Input</span>
                <span className={`setup-badge ${speechSupported ? 'granted' : 'denied'}`}>{speechSupported ? '✓ Supported' : '✗ Unsupported'}</span>
              </div>
              <p className="setup-note">{speechSupported ? 'Speech recognition available (Chrome recommended)' : 'Voice interview not supported in this browser. Use Chrome. Text fallback available.'}</p>
            </div>
            <div className={`setup-item ${speakerReady ? 'granted' : 'denied'}`}>
              <div className="setup-item-head">
                <span className="setup-icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 010 7.07"/></svg></span>
                <span className="setup-label">Speaker / AI Voice</span>
                <span className={`setup-badge ${speakerReady ? 'granted' : 'denied'}`}>{speakerReady ? '✓ Ready' : '✗ Unavailable'}</span>
              </div>
              <p className="setup-note">{speakerReady ? 'AI voice ready' : 'Speaker unavailable — questions will be shown as text'}</p>
            </div>
            <div className={`setup-item ${isFullscreen ? 'granted' : 'prompt'}`}>
              <div className="setup-item-head">
                <span className="setup-icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M8 3H5a2 2 0 00-2 2v3"/><path d="M16 3h3a2 2 0 012 2v3"/><path d="M8 21H5a2 2 0 01-2-2v-3"/><path d="M16 21h3a2 2 0 002-2v-3"/></svg></span>
                <span className="setup-label">Fullscreen</span>
                <span className={`setup-badge ${isFullscreen ? 'granted' : 'prompt'}`}>{isFullscreen ? '✓ Active' : '○ Not enabled'}</span>
              </div>
              <p className="setup-note">{isFullscreen ? 'Fullscreen active' : 'Recommended for focus — not required'}</p>
            </div>
          </div>
          <div className="setup-requirements">
            <strong>Requirements:</strong> <span className={camStatus==='granted' ? 'req-ok' : 'req-warn'}>Camera {camStatus==='granted' ? '✓' : '○'}</span> <span className={micStatus==='granted' ? 'req-ok' : 'req-warn'}>Microphone {micStatus==='granted' ? '✓' : '○'}</span> <span className={speechSupported ? 'req-ok' : 'req-warn'}>Voice {speechSupported ? '✓' : '✗'}</span> <span className={speakerReady ? 'req-ok' : 'req-warn'}>Speaker {speakerReady ? '✓' : '✗'}</span>
          </div>
          {cameraStream && (
            <div className="setup-preview">
              <video ref={cameraVideoRef} autoPlay muted playsInline className="setup-video" />
              <span className="setup-preview-label">Camera Preview</span>
            </div>
          )}
          {setupError && <div className="error-banner">{setupError}</div>}
          {error && <div className="error-banner">{error}</div>}
          {!speechSupported && <div className="setup-fallback">Voice interview is not supported in this browser. Please use Chrome or another supported browser. You can still complete the interview using text.</div>}
          <div className="setup-actions">
            <button className="btn-secondary" onClick={enableMedia}>Enable Camera & Microphone</button>
            <button className="btn-secondary" onClick={isFullscreen ? exitFullscreen : enterFullscreen}>{isFullscreen ? 'Exit Fullscreen' : 'Enter Fullscreen'}</button>
            <button className="btn-primary" onClick={handleStartInterview} disabled={!canStartInterview}>Start Interview</button>
          </div>
          {!canStartInterview && <p className="setup-hint warn">Please enable camera & microphone to continue. You can still proceed after permission is resolved.</p>}
          <p className="setup-hint">Before we begin, let's verify your interview environment. {canStartInterview ? 'You are ready to start.' : 'Enable permissions to become ready.'}</p>
        </div>
      </div>
    )
  }

  const fmt = (s) => `${String(Math.floor(s/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`

  return (
    <div className="interview-session voice" ref={containerRef}>
      <div className="session-header voice-header">
        <div className="voice-header-left">
          <div className="session-brand">◈ ARDHANARISHWAR AI</div>
          <div className="session-title">AI INTERVIEW</div>
          {interview && <div className="session-sub">{interview.job_title} • Question {qNum} of {total}</div>}
        </div>
        <div className="camera-preview">
          <video ref={cameraVideoRef} autoPlay muted playsInline className="camera-video" />
          {!cameraActive && <div className="camera-placeholder">Camera off</div>}
          <div className="camera-label">You</div>
        </div>
      </div>

      <div className="session-progress-wrap">
        <div className="session-progress-head"><span>Progress</span><span>{qNum} / {total}</span></div>
        <div className="session-progress-bar">
          <div className="session-progress-fill" style={{width: `${progress}%`}} />
        </div>
        <div className="session-meta"><span className="topic-pill">{topic}</span><span className={`diff-pill ${difficulty}`}>{difficulty}</span><span className="voice-state"><span className={`dot ${isSpeaking ? 'speaking' : isListening ? 'listening' : submitting ? 'speaking' : 'ready'}`} />{submitting ? 'Evaluating...' : isSpeaking ? 'AI Speaking' : isListening ? 'Listening' : transcript.trim() && !submitting ? 'Review your answer' : 'Ready'}</span></div>
      </div>
      <div className="interview-phase">
        {submitting ? 'Evaluating your response...' : isSpeaking ? 'AI is speaking...' : isListening ? 'Listening...' : transcript.trim() ? 'Review your answer before submitting' : 'Click Start Answer to respond'}
      </div>

      {timeRemaining !== null && (
        <div className="timer-bar">
          <span className="timer-remaining">TIME REMAINING <strong>{fmt(timeRemaining)}</strong></span>
          <span className="timer-elapsed">ELAPSED <strong>{fmt(((interview?.duration_minutes || 20) * 60) - timeRemaining)}</strong></span>
          {timeRemaining <= 60 && timeRemaining > 0 && <span className="timer-warn">● Ending soon</span>}
          {timeRemaining === 0 && <span className="timer-expired">● Time expired</span>}
        </div>
      )}

      <div className="proctor-bar">
        <span className="proctor-title">Proctoring</span>
        <span className={`proctor-dot ${cameraActive ? 'active' : 'inactive'}`}>●</span><span>Camera {cameraActive ? 'Active' : 'Inactive'}</span>
        <span className={`proctor-dot ${micIndicatorActive ? 'active' : 'inactive'}`}>●</span><span>Microphone {micIndicatorActive ? 'Active' : 'Inactive'}</span>
        <span className={`proctor-dot ${isFullscreen ? 'active' : 'inactive'}`}>●</span><span>Fullscreen {isFullscreen ? 'Active' : 'Inactive'}</span>
        <span className="proctor-warnings">Warnings: {warningsCount}</span>
        {!isFullscreen && <button className="btn-secondary small" onClick={enterFullscreen}>Enter Fullscreen</button>}
      </div>
      {proctorWarning && <div className="proctor-warning">{proctorWarning}</div>}

      <div className="question-card">
        <div className="question-label">AI INTERVIEWER {isSpeaking && <span className="speaking-badge">🔊 AI Speaking</span>}</div>
        {showQuestionText ? (
          <div className="question-text">"{questionText || 'Preparing your question...'}"</div>
        ) : (
          <div className="question-text placeholder"><span className="preparing-dot">●</span> {isSpeaking ? 'AI is speaking...' : 'AI is preparing the question...'}</div>
        )}
        {showQuestionText && isSpeaking && <div className="question-speaking-hint"><span className="preparing-dot speaking">●</span> AI is speaking...</div>}
        <button className="btn-secondary small replay-btn" onClick={handleReplay} disabled={!questionText || submitting}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 010 7.07"/><path d="M19.07 4.93a10 10 0 010 14.14"/></svg> Replay</button>
        {isSpeaking && <button className="btn-text small" onClick={stopSpeaking}>Stop</button>}
      </div>

      {error && <div className="error-banner">{error}</div>}
      {setupError && <div className="error-banner">{setupError}</div>}

      <div className="voice-controls">
        {!isListening ? (
          <button className="btn-primary voice-start" onClick={startListening} disabled={submitting || !speechSupported || isSpeaking}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10a7 7 0 01-14 0"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg> {transcript ? 'Continue Answer' : 'Start Answer'}</button>
        ) : (
          <div className="listening-box">
            <div className="listening-indicator"><span className="pulse-dot" /> Listening <span className="elapsed">{fmt(elapsed)}</span></div>
            <div className="live-transcript-label">Live transcript:</div>
            <div className="live-transcript">"{transcript || 'Listening...' }"</div>
            <button className="btn-secondary voice-stop" onClick={stopListening}>Stop Answer</button>
          </div>
        )}
        {!isListening && transcript && (
          <div className="transcript-review">
            <div className="transcript-label">Transcript:</div>
            <div className="transcript-text">"{transcript}"</div>
          </div>
        )}
        {!speechSupported && <p className="answer-hint">Voice not supported — please type or edit transcript below.</p>}
      </div>

      <form onSubmit={handleSubmit} className="answer-area">
        <label className="answer-label">Your Answer — editable transcript</label>
        <textarea
          value={transcript}
          onChange={(e)=>setTranscript(e.target.value)}
          placeholder={speechSupported ? "Transcript will appear here after speaking. You can edit before submitting..." : "Type your answer here..."}
          rows={5}
          disabled={submitting || isListening}
          className="answer-input"
        />
        <div className="answer-actions">
          <button type="button" className="btn-secondary" onClick={onBack} disabled={submitting}>Exit</button>
          <button type="button" className="btn-text" onClick={handleEnd} disabled={submitting}>End Interview</button>
          <button type="submit" className="btn-primary" disabled={submitting || !transcript.trim()}>{submitting ? 'Submitting...' : 'Submit Answer'}</button>
        </div>
        <p className="answer-hint">Answer will be evaluated for correctness, relevance, depth and clarity. Voice is primary — text remains as editable fallback.</p>
      </form>
    </div>
  )
}
