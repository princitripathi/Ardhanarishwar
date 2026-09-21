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

  const cancelSpeak = useCallback(() => {
    if (ttsSupported && typeof window !== 'undefined') {
      try { window.speechSynthesis.cancel() } catch {}
    }
    setIsSpeaking(false)
  }, [ttsSupported])

  const speak = useCallback((text) => {
    if (!ttsSupported || !text || !text.trim()) return
    // Prevent overlapping speech: cancel previous
    try { window.speechSynthesis.cancel() } catch {}
    const clean = text.trim().slice(0, 900)
    // Strip markdown-ish artifacts for more natural speech
    const plain = clean.replace(/[#*_`[\]]/g, ' ').replace(/\s+/g, ' ').trim()
    if (!plain) return
    const utter = new SpeechSynthesisUtterance(plain)
    utter.lang = 'en-US'
    utter.rate = 1
    utter.onstart = () => setIsSpeaking(true)
    utter.onend = () => setIsSpeaking(false)
    utter.onerror = () => setIsSpeaking(false)
    try { window.speechSynthesis.speak(utter) } catch { setIsSpeaking(false) }
  }, [ttsSupported])

  const stopListening = useCallback(() => {
    listeningIntent.current = false
    if (recRef.current) {
      try { recRef.current.stop() } catch {}
    }
    setIsListening(false)
    setInterim('')
  }, [])

  const startListening = useCallback((baseText = '') => {
    if (!isSupported || !recRef.current) {
      setError('Voice input is not supported in this browser. Please use Chrome or Edge on desktop, or type your message.')
      return false
    }
    // Cancel any ongoing speech before listening
    cancelSpeak()
    setError(null)
    baseRef.current = baseText || ''
    listeningIntent.current = true
    try {
      recRef.current.start()
      return true
    } catch {
      try {
        recRef.current.stop()
        setTimeout(() => {
          if (listeningIntent.current) {
            try { recRef.current.start() } catch {}
          }
        }, 120)
      } catch {}
      return true
    }
  }, [isSupported, cancelSpeak])

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
      // Only clear listening if intent was not continuous (we use non-continuous)
      if (listeningIntent.current) {
        // For false continuous, end naturally after utterance
        listeningIntent.current = false
      }
      setIsListening(false)
      setInterim('')
    }
    rec.onerror = (e) => {
      const code = e.error || 'unknown'
      listeningIntent.current = false
      setIsListening(false)
      setInterim('')
      if (code === 'not-allowed' || code === 'permission-denied') {
        setError('Microphone permission denied. Please allow microphone access or continue typing.')
      } else if (code === 'audio-capture') {
        setError('No microphone found. Please continue typing.')
      } else if (code === 'no-speech') {
        setError(null)
      } else if (code === 'aborted') {
        setError(null)
      } else {
        setError(null)
      }
    }

    recRef.current = rec
    return () => {
      listeningIntent.current = false
      try { rec.abort() } catch {}
      recRef.current = null
    }
  }, [isSupported])

  useEffect(() => {
    return () => {
      // Cleanup speech on unmount
      try { if (ttsSupported) window.speechSynthesis.cancel() } catch {}
      listeningIntent.current = false
      try { recRef.current?.abort() } catch {}
    }
  }, [ttsSupported])

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
    cancelSpeak,
    setOnFinal,
    clearError: () => setError(null)
  }
}
