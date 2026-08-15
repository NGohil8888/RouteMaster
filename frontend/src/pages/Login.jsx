import { useState } from 'react'
import { useAuthStore } from '../store'
import api from '../services/api'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isSetup, setIsSetup] = useState(false)
  const setToken = useAuthStore((s) => s.setToken)

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    try {
      const endpoint = isSetup ? '/auth/setup' : '/auth/login'
      const payload = { username, password }
      const res = await api.post(endpoint, payload)
      setToken(res.data.access_token)
      window.location.reload()
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950">
      <div className="w-full max-w-md card">
        <h1 className="text-2xl font-bold text-center mb-1 text-emerald-400">Hermes Gateway</h1>
        <p className="text-center text-gray-500 text-sm mb-6">Ollama API Router</p>
        <form onSubmit={submit} className="space-y-4">
          <input className="input" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} required />
          <input className="input" type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button type="submit" className="btn-primary w-full">{isSetup ? 'Create Admin' : 'Sign In'}</button>
        </form>
        <p className="text-center text-sm text-gray-500 mt-4">
          {isSetup ? 'Already have an account?' : 'First time?'}{' '}
          <button onClick={() => setIsSetup(!isSetup)} className="text-emerald-400 hover:underline">
            {isSetup ? 'Login' : 'Setup'}
          </button>
        </p>
      </div>
    </div>
  )
}