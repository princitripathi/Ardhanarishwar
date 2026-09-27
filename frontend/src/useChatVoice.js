import { useState, useEffect, useRef, useCallback } from 'react'

function getRecognitionCtor() {
  if (typeof window === 'undefined') return null
  return window.SpeechRecognition || window.webkitSpeechRecognition || null
}

function isRecognitionSupported() {
  return typeof window !== 'undefined' && ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)
}

function isSynthesisSupported() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window
}

export function useChatVoice() {
  const [isSupported] = useState(() => isRecognitionSupported())
  const [ttsSupported] = useState(() => isSynthesisSupported())
  const [isListening, setIsListening] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [interim, setInterim] = useState('')
  const [error, setError] = useState(null)

  const recRef = useRef(null)
  const listeningIntent = useRef(false)
  const baseRef = useRef('')
  const microphoneEnabled = useRef(false)
  const userStopped = useRef(false)
  const restartTimerRef = useRef(null)

  // TTS queue for streaming incremental speech
  const speakQueueRef = useRef([])
  const isSpeakingRef = useRef(false)
  const playNextRef = useRef(null)

  const cancelSpeak = useCallback(() => {
    // Clear queued utterances and stop current
    speakQueueRef.current = []
    isSpeakingRef.current = false
    if (ttsSupported && typeof window !== 'undefined') {
      try { window.speechSynthesis.cancel() } catch {}
    }
    setIsSpeaking(false)
  }, [ttsSupported])

  const clearRestartTimer = useCallback(() => {
    if (restartTimerRef.current) {
      clearTimeout(restartTimerRef.current)
      restartTimerRef.current = null
    }
  }, [])

  const _playNext = useCallback(() => {
    if (!ttsSupported || typeof window === 'undefined') return
    if (isSpeakingRef.current) return
    const next = speakQueueRef.current.shift()
    if (!next) {
      setIsSpeaking(false)
      isSpeakingRef.current = false
      return
    }
    const clean = next.trim().slice(0, 900)
    const plain = clean.replace(/[#*_`[\]]/g, ' ').replace(/\s+/g, ' ').trim()
    if (!plain) {
      // Skip empty and try next
      setTimeout(() => playNextRef.current?.(), 0)
      return
    }
    const utter = new SpeechSynthesisUtterance(plain)
    utter.lang = 'en-US'
    utter.rate = 1
    isSpeakingRef.current = true
    setIsSpeaking(true)
    utter.onstart = () => {
      isSpeakingRef.current = true
      setIsSpeaking(true)
    }
    utter.onend = () => {
      isSpeakingRef.current = false
      setIsSpeaking(false)
      // Small delay to let next queued speak
      setTimeout(() => playNextRef.current?.(), 30)
    }
    utter.onerror = () => {
      isSpeakingRef.current = false
      setIsSpeaking(false)
      setTimeout(() => playNextRef.current?.(), 30)
    }
    try { window.speechSynthesis.speak(utter) } catch {
      isSpeakingRef.current = false
      setIsSpeaking(false)
      setTimeout(() => playNextRef.current?.(), 30)
    }
  }, [ttsSupported])

  // Keep ref updated for recursive calls
  useEffect(() => { playNextRef.current = _playNext }, [_playNext])

  const queueSpeak = useCallback((text) => {
    if (!ttsSupported || !text || !text.trim()) return
    const clean = text.trim()
    if (!clean) return
    speakQueueRef.current.push(clean)
    // If not currently speaking, start playback
    if (!isSpeakingRef.current) {
      // Use ref to avoid stale closure
      if (playNextRef.current) playNextRef.current()
      else _playNext()
    }
  }, [ttsSupported, _playNext])

  const speak = useCallback((text) => {
    if (!ttsSupported || !text || !text.trim()) return
    // For non-streaming fallback, use queue path to avoid overlap: cancel then queue single
    try { window.speechSynthesis.cancel() } catch {}
    speakQueueRef.current = []
    isSpeakingRef.current = false
    const clean = text.trim().slice(0, 900)
    // Strip markdown-ish artifacts for more natural speech
    const plain = clean.replace(/[#*_`[\]]/g, ' ').replace(/\s+/g, ' ').trim()
    if (!plain) return
    const utter = new SpeechSynthesisUtterance(plain)
    utter.lang = 'en-US'
    utter.rate = 1
    utter.onstart = () => {
      isSpeakingRef.current = true
      setIsSpeaking(true)
    }
    utter.onend = () => {
      isSpeakingRef.current = false
      setIsSpeaking(false)
      // If queued items remain (fallback queue), play next
      if (speakQueueRef.current.length > 0) _playNext()
    }
    utter.onerror = () => {
      isSpeakingRef.current = false
      setIsSpeaking(false)
    }
    isSpeakingRef.current = true
    setIsSpeaking(true)
    try { window.speechSynthesis.speak(utter) } catch {
      isSpeakingRef.current = false
      setIsSpeaking(false)
    }
  }, [ttsSupported, _playNext])

  const stopListening = useCallback(() => {
    microphoneEnabled.current = false
    userStopped.current = true
    listeningIntent.current = false
    clearRestartTimer()
    if (recRef.current) {
      try { recRef.current.stop() } catch {}
    }
    setIsListening(false)
    setInterim('')
  }, [clearRestartTimer])

  const startListening = useCallback((baseText = '') => {
    if (!isSupported || !recRef.current) {
      setError('Voice input is not supported in this browser. Please use Chrome or Edge on desktop, or type your message.')
      return false
    }
    // Cancel any ongoing speech before listening
    cancelSpeak()
    setError(null)
    baseRef.current = baseText || ''
    microphoneEnabled.current = true
    userStopped.current = false
    listeningIntent.current = true
    try {
      recRef.current.start()
      return true
    } catch {
      try {
        recRef.current.stop()
        clearRestartTimer()
        restartTimerRef.current = setTimeout(() => {
          if (microphoneEnabled.current && listeningIntent.current && !userStopped.current) {
            try { recRef.current.start() } catch {}
          }
        }, 120)
      } catch {}
      return true
    }
  }, [isSupported, cancelSpeak, clearRestartTimer])

  useEffect(() => {
    if (!isSupported) return
    const Ctor = getRecognitionCtor()
    if (!Ctor) return
    const rec = new Ctor()
    rec.continuous = false
    rec.interimResults = true
    rec.lang = 'en-US'
    rec.maxAlternatives = 1

    rec.onstart = () => {
      setIsListening(true)
      setInterim('')
      setError(null)
    }
    rec.onresult = (event) => {
      let interimText = ''
      let finalText = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const res = event.results[i]
        const txt = res[0]?.transcript || ''
        if (res.isFinal) finalText += txt + ' '
        else interimText += txt + ' '
      }
      if (interimText) setInterim(interimText.trim())
      if (finalText) {
        const base = baseRef.current ? baseRef.current.trim() : ''
        const combined = base ? `${base} ${finalText.trim()}`.trim() : finalText.trim()
        // Signal via custom event on window? We use callback via setting interim then consumer reads.
        // Instead we update interim to final and let consumer handle commit.
        // We'll store final in a way consumer can read: setInterim to final and trigger onEnd commit.
        // For now just keep interim as final until onend.
        setInterim(finalText.trim())
        // store pending final for onend
        rec._pendingFinal = combined
      }
    }
    rec.onend = () => {
      const pending = rec._pendingFinal
      rec._pendingFinal = null
      if (pending != null) {
        // This will be handled by onFinal callback if set
        if (rec._onFinal) rec._onFinal(pending)
      }
      // Only continue listening if microphone is explicitly enabled by user AND user didn't explicitly stop
      if (microphoneEnabled.current && !userStopped.current) {
        // For non-continuous mode, restart to allow next utterance
        listeningIntent.current = true
        clearRestartTimer()
        restartTimerRef.current = setTimeout(() => {
          if (microphoneEnabled.current && listeningIntent.current && !userStopped.current && recRef.current) {
            try { recRef.current.start() } catch {}
          }
        }, 250)
        // Keep isListening true to keep UI in listening state
        return
      }
      // Microphone was turned OFF by user - stop completely
      listeningIntent.current = false
      setIsListening(false)
      setInterim('')
      // Reset userStopped flag after handling the stop
      userStopped.current = false
    }
    rec.onerror = (e) => {
      const code = e.error || 'unknown'
      // If microphone was explicitly turned OFF, don't treat errors as restart triggers
      if (!microphoneEnabled.current) {
        listeningIntent.current = false
        setIsListening(false)
        setInterim('')
        return
      }
      listeningIntent.current = false
      setIsListening(false)
      setInterim('')
      if (code === 'not-allowed' || code === 'permission-denied') {
        setError('Microphone permission denied. Please allow microphone access or continue typing.')
        microphoneEnabled.current = false
      } else if (code === 'audio-capture') {
        setError('No microphone found. Please continue typing.')
        microphoneEnabled.current = false
      } else if (code === 'no-speech') {
        setError(null)
        // No speech is natural pause - restart if microphone still enabled and user didn't stop
        if (microphoneEnabled.current && !userStopped.current) {
          clearRestartTimer()
          restartTimerRef.current = setTimeout(() => {
            if (microphoneEnabled.current && listeningIntent.current && !userStopped.current && recRef.current) {
              try { recRef.current.start() } catch {}
            }
          }, 300)
        }
      } else if (code === 'aborted') {
        setError(null)
      } else {
        setError(null)
        // For other errors, try restart if microphone still enabled and user didn't stop
        if (microphoneEnabled.current && !userStopped.current) {
          clearRestartTimer()
          restartTimerRef.current = setTimeout(() => {
            if (microphoneEnabled.current && listeningIntent.current && !userStopped.current && recRef.current) {
              try { recRef.current.start() } catch {}
            }
          }, 400)
        }
      }
    }

    recRef.current = rec
    return () => {
      microphoneEnabled.current = false
      userStopped.current = false
      listeningIntent.current = false
      clearRestartTimer()
      try { rec.abort() } catch {}
      recRef.current = null
    }
  }, [isSupported, clearRestartTimer])

  useEffect(() => {
    return () => {
      // Cleanup speech on unmount
      try { if (ttsSupported) window.speechSynthesis.cancel() } catch {}
      microphoneEnabled.current = false
      listeningIntent.current = false
      clearRestartTimer()
      try { recRef.current?.abort() } catch {}
    }
  }, [ttsSupported, clearRestartTimer])

  const setOnFinal = useCallback((cb) => {
    if (recRef.current) recRef.current._onFinal = cb
  }, [])

  return {
    isSupported,
    ttsSupported,
    isListening,
    isSpeaking,
    interim,
    error,
    startListening,
    stopListening,
    speak,
    queueSpeak,
    cancelSpeak,
    setOnFinal,
    clearError: () => setError(null)
  }
}
