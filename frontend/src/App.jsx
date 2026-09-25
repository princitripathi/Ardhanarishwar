import { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import { checkBackendHealth, sendChatMessage, sendChatMessageStream } from './api'
import { InterviewSchedule, InterviewScheduledCard, InterviewLobby, InterviewList } from './InterviewViews'
import { InterviewSession } from './InterviewSession'
import { useChatVoice } from './useChatVoice'
import './App.css'

const suggestions = [
  { label: 'Career planning', prompt: 'Help me plan my career growth for the next 2 years' },
  { label: 'Improve my resume', prompt: 'How can I improve my resume for a software engineer role?' },
  { label: 'Prepare for an interview', prompt: 'Help me prepare for an AI/ML interview' },
  { label: 'Learn a new skill', prompt: 'I want to learn a new skill, where should I start?' },
]

function getAgentMeta(intent) {
  const map = {
    career: { label: 'Career' },
    resume: { label: 'Resume' },
    interview: { label: 'Interview' },
    learning: { label: 'Learning' },
    recruitment: { label: 'Recruitment' },
    business: { label: 'Business' },
  }
  return map[intent] || null
}

function MarkdownContent({ text }) {
  if (!text) return null
  return (
    <div className="markdown">
      <ReactMarkdown
        components={{
          h1: ({ ...props }) => <h1 className="md-h1" {...props} />,
          h2: ({ ...props }) => <h2 className="md-h2" {...props} />,
          h3: ({ ...props }) => <h3 className="md-h3" {...props} />,
          p: ({ ...props }) => <p className="md-p" {...props} />,
          ul: ({ ...props }) => <ul className="md-ul" {...props} />,
          ol: ({ ...props }) => <ol className="md-ol" {...props} />,
          li: ({ ...props }) => <li className="md-li" {...props} />,
          strong: ({ ...props }) => <strong {...props} />,
          em: ({ ...props }) => <em {...props} />,
          a: ({ ...props }) => <a className="md-link" target="_blank" rel="noopener noreferrer" {...props} />,
          code: ({ inline, children, ...props }) => {
            if (inline) return <code className="md-inline-code" {...props}>{children}</code>
            return <code className="md-code-block" {...props}>{children}</code>
          },
          pre: ({ ...props }) => <pre className="md-pre" {...props} />,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}

function IconChat(props) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M21 11.5a2.5 2.5 0 0 1-2.5 2.5H10l-4 4v-9a2.5 2.5 0 0 1 2.5-2.5h10A2.5 2.5 0 0 1 21 11.5Z" />
    </svg>
  )
}
function IconBriefcase(props) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" {...props}>
      <rect x="3" y="7" width="18" height="12" rx="1.5" />
      <path d="M8 7V5.5a2.5 2.5 0 0 1 2.5-2.5h3A2.5 2.5 0 0 1 16 5.5V7" />
      <path d="M3 11.5h18" />
    </svg>
  )
}
function IconPlus(props) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" {...props}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  )
}

function App() {
  const [status, setStatus] = useState('checking')
  const [messages, setMessages] = useState([])
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [interviewView, setInterviewView] = useState('chat')
  const [scheduledInterviewId, setScheduledInterviewId] = useState(null)
  const [lobbyInterviewId, setLobbyInterviewId] = useState(null)
  const [sessionInterviewId, setSessionInterviewId] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [autoSpeak, setAutoSpeak] = useState(true)
  const voice = useChatVoice()
  const [conversationId, setConversationId] = useState(() => {
    try {
      const stored = localStorage.getItem('ard_conversation_id')
      if (stored) return stored
    } catch {}
    const id = (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36)
    try { localStorage.setItem('ard_conversation_id', id) } catch {}
    return id
  })
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)
  const [voiceBase, setVoiceBase] = useState('')
  const ttsBufferRef = useRef('')

  useEffect(() => {
    let mounted = true
    async function fetchHealth() {
      try {
        await checkBackendHealth()
        if (mounted) setStatus('connected')
      } catch {
        if (mounted) setStatus('disconnected')
      }
    }
    fetchHealth()
    const id = setInterval(fetchHealth, 30000)
    return () => {
      mounted = false
      clearInterval(id)
    }
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Chat voice: handle final transcript -> input, preserve typed text
  useEffect(() => {
    voice.setOnFinal((finalText) => {
      if (finalText != null) {
        setInputValue(finalText)
        // focus for editing before send
        setTimeout(() => inputRef.current?.focus(), 50)
      }
    })
  }, [voice])

  // Stop speech when starting to type or sending
  useEffect(() => {
    if (voice.isListening && voice.isSpeaking) voice.cancelSpeak()
  }, [voice.isListening]) // eslint-disable-line react-hooks/exhaustive-deps

  const sendMessage = async (text) => {
    const message = text.trim()
    if (!message || isLoading) return

    // Prevent overlapping speech: cancel any ongoing TTS before new turn and reset streaming buffer
    ttsBufferRef.current = ''
    if (voice.isSpeaking) voice.cancelSpeak()
    if (voice.isListening) voice.stopListening()

    setMessages((prev) => [...prev, { role: 'user', content: message }])
    setIsLoading(true)
    setError(null)

    const assistantIdxRef = { current: null }
    let streamContent = ''
    let streamIntent = null
    let streamAgent = null
    let gotChunk = false

    setMessages((prev) => {
      assistantIdxRef.current = prev.length
      return [...prev, { role: 'assistant', content: '', model: 'qwen2.5:3b', intent: null, agent: null, streaming: true }]
    })

    const updateAssistant = (content, intent, agent, streaming) => {
      setMessages((prev) => {
        const idx = assistantIdxRef.current
        if (idx === null || idx >= prev.length) return prev
        const updated = [...prev]
        updated[idx] = {
          ...updated[idx],
          content,
          intent: intent !== undefined ? intent : updated[idx].intent,
          agent: agent !== undefined ? agent : updated[idx].agent,
          streaming,
        }
        return updated
      })
    }

    // Streaming TTS helpers: split buffer into complete sentences/phrases for natural speech
    const extractComplete = (buffer) => {
      if (!buffer || !buffer.trim()) return { sentences: [], remainder: buffer }
      const sentences = []
      // Capture sentences ending with .!? or newline
      const re = /[^.!?\n]+[.!?]+(?:\s+|$)|[^\n]+\n+/g
      let lastIndex = 0
      let m
      while ((m = re.exec(buffer)) !== null) {
        const s = m[0].trim()
        if (s) sentences.push(s)
        lastIndex = re.lastIndex
      }
      let remainder = buffer.slice(lastIndex)
      // Fallback: if no complete sentence but buffer is long, split on last space to avoid indefinite buffering
      if (sentences.length === 0 && remainder.trim().length > 140) {
        const lastSpace = remainder.lastIndexOf(' ')
        if (lastSpace > 80) {
          const chunk = remainder.slice(0, lastSpace).trim()
          if (chunk) sentences.push(chunk)
          remainder = remainder.slice(lastSpace + 1)
        }
      }
      return { sentences, remainder }
    }

    const shouldStreamSpeak = autoSpeak && voice.ttsSupported

    try {
      await sendChatMessageStream(message, {
        onMeta: (meta) => {
          streamIntent = meta.intent
          streamAgent = meta.agent
          if (meta.conversation_id && meta.conversation_id !== conversationId) {
            setConversationId(meta.conversation_id)
            try { localStorage.setItem('ard_conversation_id', meta.conversation_id) } catch {}
          }
          updateAssistant(streamContent, streamIntent, streamAgent, true)
        },
        onChunk: (chunk) => {
          gotChunk = true
          streamContent += chunk
          if (gotChunk) setIsLoading(false)
          updateAssistant(streamContent, streamIntent, streamAgent, true)
          // Streaming TTS: enqueue complete sentences as they become available, don't wait for full response
          if (shouldStreamSpeak && chunk && !chunk.startsWith('Error:')) {
            ttsBufferRef.current += chunk
            const { sentences, remainder } = extractComplete(ttsBufferRef.current)
            if (sentences.length > 0) {
              ttsBufferRef.current = remainder
              sentences.forEach((s) => voice.queueSpeak(s))
            }
          }
        },
        onError: (detail) => {
          throw new Error(detail)
        },
        conversationId,
      })
      if (!gotChunk) {
        const data = await sendChatMessage(message, conversationId)
        if (data.conversation_id && data.conversation_id !== conversationId) {
          setConversationId(data.conversation_id)
          try { localStorage.setItem('ard_conversation_id', data.conversation_id) } catch {}
        }
        updateAssistant(data.response, data.intent, data.agent, false)
        if (shouldStreamSpeak && data.response && !data.response.startsWith('Error:')) {
          // For non-stream fallback, queue single utterance via streaming queue to keep behavior consistent
          ttsBufferRef.current = ''
          voice.queueSpeak(data.response)
        }
      } else {
        const finalStream = streamContent || '(no response)'
        updateAssistant(finalStream, streamIntent, streamAgent, false)
        // Flush any remaining buffered text after stream completion; do NOT re-speak entire finalStream (prevents duplicate)
        if (shouldStreamSpeak && ttsBufferRef.current.trim()) {
          const remaining = ttsBufferRef.current.trim()
          ttsBufferRef.current = ''
          if (remaining && !remaining.startsWith('Error:')) {
            voice.queueSpeak(remaining)
          }
        }
      }
    } catch (err) {
      // On streaming error, cancel pending TTS and clear buffer to avoid stale speech
      ttsBufferRef.current = ''
      if (voice.isSpeaking) voice.cancelSpeak()
      if (!gotChunk) {
        try {
          const data = await sendChatMessage(message, conversationId)
          if (data.conversation_id && data.conversation_id !== conversationId) {
            setConversationId(data.conversation_id)
            try { localStorage.setItem('ard_conversation_id', data.conversation_id) } catch {}
          }
          updateAssistant(data.response, data.intent, data.agent, false)
          if (shouldStreamSpeak && data.response && !data.response.startsWith('Error:')) {
            voice.queueSpeak(data.response)
          }
        } catch (fallbackErr) {
          setError(fallbackErr.message)
          updateAssistant(`Error: ${fallbackErr.message}`, null, null, false)
          setMessages((prev) => {
            const idx = assistantIdxRef.current
            if (idx !== null && prev[idx]) prev[idx].isError = true
            return [...prev]
          })
        }
      } else {
        setError(err.message)
        updateAssistant(streamContent + `\n\nError: ${err.message}`, streamIntent, streamAgent, false)
      }
    } finally {
      setIsLoading(false)
      inputRef.current?.focus()
    }
  }

  const handleSend = async (e) => {
    e.preventDefault()
    if (voice.isListening) voice.stopListening()
    if (voice.isSpeaking) {
      voice.cancelSpeak()
      ttsBufferRef.current = ''
    }
    const text = voice.isListening ? (voiceBase || inputValue) : inputValue
    const finalText = text.trim()
    if (!finalText) return
    setInputValue('')
    setVoiceBase('')
    await sendMessage(finalText)
  }

  const handleVoiceToggle = () => {
    if (voice.isListening) {
      voice.stopListening()
      return
    }
    // Preserve typed text
    setVoiceBase(inputValue)
    voice.startListening(inputValue)
  }

  const handleInputChange = (e) => {
    setInputValue(e.target.value)
    // If user types while speaking, cancel speech to prevent overlap
    if (voice.isSpeaking) {
      voice.cancelSpeak()
      ttsBufferRef.current = ''
    }
  }

  // Display value: preserve typed text + interim transcript when listening
  const displayValue = voice.isListening && voice.interim
    ? (voiceBase ? `${voiceBase} ${voice.interim}`.trim() : voice.interim)
    : inputValue

  const handleSuggestion = (prompt) => {
    if (voice.isSpeaking) {
      voice.cancelSpeak()
      ttsBufferRef.current = ''
    }
    if (voice.isListening) voice.stopListening()
    sendMessage(prompt)
  }

  const handleNewChat = () => {
    if (voice.isListening) voice.stopListening()
    if (voice.isSpeaking) voice.cancelSpeak()
    ttsBufferRef.current = ''
    setMessages([])
    setError(null)
    setInputValue('')
    setVoiceBase('')
    const id = (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36)
    setConversationId(id)
    try { localStorage.setItem('ard_conversation_id', id) } catch {}
    setInterviewView('chat')
    setSidebarOpen(false)
  }

  const isInterviewMode = interviewView !== 'chat'

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <div className="header-left">
            <button className="sidebar-toggle" aria-label="Toggle sidebar" onClick={() => setSidebarOpen(o => !o)}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
            </button>
            <div className="brand">
              <div className="brand-mark">◈</div>
              <div className="brand-text">
                <span className="brand-name">Ardhanarishwar Solver</span>
                <span className="brand-sub">AI Career & Professional Assistant</span>
              </div>
            </div>
          </div>
          <div className="header-status" title={status === 'connected' ? 'Backend connected' : status === 'checking' ? 'Checking...' : 'Backend unavailable'}>
            <span className={`status-dot ${status}`} />
            <span className="status-label">{status === 'connected' ? 'AI Online' : status === 'checking' ? 'Connecting…' : 'Offline'}</span>
          </div>
        </div>
      </header>

      <div className="app-layout">
        <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
          <button className="new-chat-btn" onClick={handleNewChat}>
            <IconPlus /> New chat
          </button>

          <nav className="sidebar-nav" aria-label="Primary">
            <button className={`side-nav-item ${interviewView === 'chat' ? 'active' : ''}`} onClick={() => { setInterviewView('chat'); setSidebarOpen(false) }}>
              <IconChat /> Chat
            </button>
            <button className={`side-nav-item ${isInterviewMode ? 'active' : ''}`} onClick={() => { setInterviewView('schedule'); setSidebarOpen(false) }}>
              <IconBriefcase /> AI Interview
            </button>
          </nav>

          <div className="sidebar-section">
            <div className="sidebar-label">Recent</div>
            {messages.length === 0 ? (
              <div className="recent-empty">No conversations yet</div>
            ) : (
              <div className="recent-list">
                {messages.filter(m => m.role === 'user').slice(-4).reverse().map((m, i) => (
                  <div key={i} className="recent-item" title={m.content}>
                    <IconChat />
                    <span>{m.content.slice(0, 38)}{m.content.length > 38 ? '…' : ''}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="sidebar-footer">
            <div className="sidebar-hint">Conversations are local to this browser.</div>
          </div>
        </aside>

        {sidebarOpen && <button className="sidebar-backdrop" aria-label="Close sidebar" onClick={() => setSidebarOpen(false)} />}

        <div className="main-column">
          <main className="main">
            {interviewView === 'schedule' ? (
              <div className="workspace workspace-interview">
                <InterviewSchedule
                  onScheduled={(id) => { setScheduledInterviewId(id); setLobbyInterviewId(id); setInterviewView('scheduled') }}
                  onCancelView={() => setInterviewView('chat')}
                />
                <div className="workspace-footer">
                  <button className="btn-text" onClick={() => setInterviewView('list')}>View scheduled interviews</button>
                </div>
              </div>
            ) : interviewView === 'scheduled' && scheduledInterviewId ? (
              <div className="workspace workspace-interview">
                <InterviewScheduledCard
                  interviewId={scheduledInterviewId}
                  onView={(id) => { setLobbyInterviewId(id); setInterviewView('lobby') }}
                />
                <div className="workspace-footer">
                  <button className="btn-secondary" onClick={() => setInterviewView('chat')}>Back to chat</button>
                  <button className="btn-text" onClick={() => setInterviewView('list')}>View all interviews</button>
                </div>
              </div>
            ) : interviewView === 'lobby' && lobbyInterviewId ? (
              <div className="workspace workspace-interview">
                <InterviewLobby
                  interviewId={lobbyInterviewId}
                  onBack={() => setInterviewView('list')}
                  onStartSession={(id) => { setSessionInterviewId(id); setInterviewView('session') }}
                />
              </div>
            ) : interviewView === 'session' && sessionInterviewId ? (
              <div className="workspace workspace-interview workspace-session">
                <InterviewSession
                  interviewId={sessionInterviewId}
                  onBack={() => setInterviewView('lobby')}
                  onComplete={() => {}}
                />
              </div>
            ) : interviewView === 'list' ? (
              <div className="workspace workspace-interview">
                <div className="workspace-head">
                  <h2>AI Interview</h2>
                  <span>Scheduled interviews</span>
                </div>
                <InterviewList onSelect={(id) => { setLobbyInterviewId(id); setInterviewView('lobby') }} onClose={() => setInterviewView('chat')} />
                <div className="workspace-footer">
                  <button className="btn-primary" onClick={() => setInterviewView('schedule')}>Schedule new interview</button>
                  <button className="btn-secondary" onClick={() => setInterviewView('chat')}>Back to chat</button>
                </div>
              </div>
            ) : (
              <div className="workspace workspace-chat">
                <div className="messages-area">
                  {messages.length === 0 ? (
                    <div className="welcome">
                      <h1 className="welcome-title">How can I help you today?</h1>
                      <p className="welcome-subtitle">Ask about career growth, resumes, interviews, or learning paths.</p>
                      <div className="suggestion-chips">
                        {suggestions.map((s) => (
                          <button key={s.label} className="chip" onClick={() => handleSuggestion(s.prompt)} disabled={status === 'disconnected' || isLoading}>
                            {s.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="messages">
                      {messages.map((msg, idx) => {
                        if (msg.role === 'user') {
                          return (
                            <div key={idx} className="msg-row user">
                              <div className="bubble bubble-user">{msg.content}</div>
                            </div>
                          )
                        }
                        const agentMeta = msg.intent ? getAgentMeta(msg.intent) : null
                        const showThinking = msg.streaming && !msg.content
                        return (
                          <div key={idx} className={`msg-row assistant ${msg.isError ? 'error' : ''}`}>
                            <div className="assistant-avatar">◈</div>
                            <div className="bubble bubble-assistant">
                              <div className="assistant-label">Ardhanarishwar Solver</div>
                              {showThinking ? (
                                <div className="thinking">
                                  <span>Thinking</span>
                                  <span className="dots"><i></i><i></i><i></i></span>
                                </div>
                              ) : (
                                <div className="bubble-content"><MarkdownContent text={msg.content} /></div>
                              )}
                              {(msg.intent || msg.model) && !showThinking && (
                                <div className="meta-badges">
                                  {agentMeta && (
                                    <span className="badge badge-agent">{agentMeta.label}</span>
                                  )}
                                  {!agentMeta && msg.intent && (
                                    <span className="badge badge-agent">{msg.intent}</span>
                                  )}
                                  {msg.model && <span className="badge badge-model">{msg.model === 'qwen2.5:3b' ? 'Qwen 2.5 3B' : msg.model}</span>}
                                </div>
                              )}
                            </div>
                          </div>
                        )
                      })}
                      <div ref={messagesEndRef} />
                    </div>
                  )}
                </div>

                <div className="composer-wrap">
                  {error && <div className="error-banner">{error}</div>}
                  {voice.error && <div className="error-banner voice-error" role="status">{voice.error}</div>}
                  {!voice.isSupported && (
                    <div className="voice-unsupported" role="status">
                      Voice input is not available in this browser. Please use Chrome or Edge on desktop, or continue typing.
                    </div>
                  )}
                  {voice.isListening && (
                    <div className="voice-listening-indicator" role="status" aria-live="polite">
                      <span className="voice-dot" /> Listening — speak now
                    </div>
                  )}
                  <form onSubmit={handleSend} className={`composer ${voice.isListening ? 'composer--listening' : ''} ${voice.isSpeaking ? 'composer--speaking' : ''}`}>
                    <input
                      ref={inputRef}
                      type="text"
                      value={displayValue}
                      onChange={handleInputChange}
                      placeholder={voice.isListening ? 'Listening…' : 'Ask anything…'}
                      disabled={isLoading || status === 'disconnected'}
                      className="composer-input"
                      aria-label="Message input"
                    />
                    {voice.isSupported && (
                      <button
                        type="button"
                        onClick={handleVoiceToggle}
                        disabled={isLoading || status === 'disconnected'}
                        className={`composer-mic ${voice.isListening ? 'mic--listening' : ''}`}
                        aria-label={voice.isListening ? 'Stop recording' : 'Start voice input'}
                        title={voice.isListening ? 'Stop recording' : 'Start voice input'}
                      >
                        {voice.isListening ? (
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="6" y="4" width="12" height="12" rx="2" /><line x1="12" y1="16" x2="12" y2="22" /><line x1="8" y1="22" x2="16" y2="22" /></svg>
                        ) : (
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 14a3 3 0 003-3V6a3 3 0 00-6 0v5a3 3 0 003 3z" /><path d="M19 10a7 7 0 01-14 0" /><line x1="12" y1="19" x2="12" y2="22" /><line x1="8" y1="22" x2="16" y2="22" /></svg>
                        )}
                      </button>
                    )}
                    {voice.isSpeaking && (
                      <button
                        type="button"
                        onClick={() => voice.cancelSpeak()}
                        className="composer-mic mic--stop"
                        aria-label="Stop speaking"
                        title="Stop speaking"
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="6" y="6" width="12" height="12" rx="1" /></svg>
                      </button>
                    )}
                    {!voice.isSpeaking && voice.ttsSupported && messages.length > 0 && (
                      <button
                        type="button"
                        onClick={() => setAutoSpeak(v => !v)}
                        className={`composer-mic ${autoSpeak ? 'mic--active' : ''}`}
                        aria-label={autoSpeak ? 'Mute voice output' : 'Enable voice output'}
                        title={autoSpeak ? 'Mute voice output' : 'Enable voice output'}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" /><path d={autoSpeak ? 'M15.54 8.46a5 5 0 010 7.07' : 'M23 9l-6 6M17 9l6 6'} /></svg>
                      </button>
                    )}
                    <button type="submit" disabled={isLoading || !displayValue.trim() || status === 'disconnected'} className="composer-send" aria-label="Send">
                      {isLoading ? (
                        <span className="send-spinner" />
                      ) : (
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 2L11 13" /><path d="M22 2L15 22L11 13L2 9L22 2Z" /></svg>
                      )}
                    </button>
                  </form>
                  <div className="composer-hint">
                    {status === 'disconnected' ? 'Backend is disconnected. Please start the backend server.' : voice.isListening ? 'Listening — press mic to stop' : 'Press Enter to send · Mic for voice input'}
                  </div>
                </div>
              </div>
            )}
          </main>
        </div>
      </div>
    </div>
  )
}

export default App
