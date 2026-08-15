import { useState, useEffect } from 'react'
import api from '../services/api'
import { useAppStore } from '../store'

const modes = ['AUTO', 'ROUND_ROBIN', 'LEAST_LOAD', 'FASTEST_SERVER', 'PRIORITY', 'MANUAL', 'FAILOVER_ONLY']

export default function Settings() {
  const { routingMode, setRoutingMode } = useAppStore()
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.get('/dashboard/routing-mode').then((res) => setRoutingMode(res.data.mode))
  }, [])

  const changeMode = async (mode) => {
    setSaving(true)
    await api.post('/dashboard/routing-mode', { routing_mode: mode })
    setRoutingMode(mode)
    setSaving(false)
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Settings</h2>
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Routing Mode</h3>
        <p className="text-sm text-gray-500 mb-4">Select how Hermes routes requests across Ollama servers.</p>
        <div className="grid grid-cols-4 gap-3">
          {modes.map((m) => (
            <button
              key={m}
              onClick={() => changeMode(m)}
              disabled={saving}
              className={`p-3 rounded-lg border text-sm font-medium transition-colors ${
                routingMode === m
                  ? 'bg-emerald-900/30 border-emerald-600 text-emerald-400'
                  : 'bg-gray-800 border-gray-700 text-gray-400 hover:bg-gray-700'
              }`}
            >
              {m.replace(/_/g, ' ')}
            </button>
          ))}
        </div>
        <p className="text-xs text-gray-600 mt-3">Current: <span className="text-emerald-400">{routingMode}</span></p>
      </div>
    </div>
  )
}