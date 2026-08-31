import { useState, useEffect } from 'react'
import { checkBackendHealth } from './api'
import './App.css'

function App() {
  const [status, setStatus] = useState('checking')
  const [backendInfo, setBackendInfo] = useState(null)

  useEffect(() => {
    let mounted = true

    async function fetchHealth() {
      try {
        const data = await checkBackendHealth()
        if (mounted) {
          setStatus('connected')
          setBackendInfo(data)
        }
      } catch {
        if (mounted) {
          setStatus('disconnected')
        }
      }
    }

    fetchHealth()

    return () => {
      mounted = false
    }
  }, [])

  return (
    <div className="app">
      <h1>Ardhanarishwar</h1>
      <div className="status-section">
        <h2>Backend Status</h2>
        <div className={`status-indicator ${status}`}>
          {status === 'checking' && 'Checking backend...'}
          {status === 'connected' && (
            <>
              <span className="dot"></span>
              Connected
            </>
          )}
          {status === 'disconnected' && (
            <>
              <span className="dot"></span>
              Backend unavailable
            </>
          )}
        </div>
        {backendInfo && (
          <div className="backend-info">
            <p>Backend: {backendInfo.service}</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default App