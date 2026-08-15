import { useEffect, useState } from 'react'
import api from '../services/api'
import { useAppStore } from '../store'
import { Plus, Edit2, Trash2, TestTube, Power } from 'lucide-react'

export default function Servers() {
  const { servers, setServers } = useAppStore()
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({
    name: '', url: '', api_key: '',
    priority: 5, weight: 1,
    max_concurrent: 10, timeout_seconds: 120
  })

  const load = async () => {
    const res = await api.get('/servers/status')
    setServers(res.data)
  }

  useEffect(() => { load() }, [])

  const save = async (e) => {
    e.preventDefault()
    if (editing) {
      await api.put(`/servers/${editing.id}`, form)
    } else {
      await api.post('/servers', form)
    }
    setShowForm(false)
    setEditing(null)
    setForm({ name: '', url: '', api_key: '', priority: 5, weight: 1, max_concurrent: 10, timeout_seconds: 120 })
    load()
  }

  const remove = async (id) => {
    if (!confirm('Delete this server?')) return
    await api.delete(`/servers/${id}`)
    load()
  }

  const test = async (id) => {
    const res = await api.post(`/servers/${id}/test`)
    alert(res.data.healthy
      ? `Healthy! Latency: ${Math.round(res.data.latency_ms)}ms, Models: ${res.data.models.length}`
      : `Unhealthy: ${res.data.error}`)
  }

  const toggle = async (s) => {
    await api.put(`/servers/${s.id}`, { enabled: !s.enabled })
    load()
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Ollama Servers</h2>
        <button onClick={() => setShowForm(true)} className="btn-primary flex items-center gap-2">
          <Plus size={18} /> Add Server
        </button>
      </div>

      {showForm && (
        <div className="card">
          <h3 className="text-lg font-semibold mb-4">{editing ? 'Edit' : 'Add'} Server</h3>
          <form onSubmit={save} className="grid grid-cols-2 gap-4">
            <input className="input" placeholder="Name" value={form.name} onChange={(e) => setForm({...form, name: e.target.value})} required />
            <input className="input" placeholder="URL (http://...)" value={form.url} onChange={(e) => setForm({...form, url: e.target.value})} required />
            <input className="input" placeholder="API Key (optional)" value={form.api_key} onChange={(e) => setForm({...form, api_key: e.target.value})} />
            <input className="input" type="number" placeholder="Priority" value={form.priority} onChange={(e) => setForm({...form, priority: parseInt(e.target.value)})} />
            <input className="input" type="number" placeholder="Weight" value={form.weight} onChange={(e) => setForm({...form, weight: parseInt(e.target.value)})} />
            <input className="input" type="number" placeholder="Max Concurrent" value={form.max_concurrent} onChange={(e) => setForm({...form, max_concurrent: parseInt(e.target.value)})} />
            <div className="col-span-2 flex gap-2">
              <button type="submit" className="btn-primary">{editing ? 'Update' : 'Create'}</button>
              <button type="button" onClick={() => { setShowForm(false); setEditing(null); }} className="btn-secondary">Cancel</button>
            </div>
          </form>
        </div>
      )}

      <div className="space-y-3">
        {servers.map((s) => (
          <div key={s.id} className="card flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-semibold">{s.name}</h3>
                <span className={`badge ${s.is_healthy ? 'badge-green' : 'badge-red'}`}>{s.is_healthy ? 'Healthy' : 'Down'}</span>
                {!s.enabled && <span className="badge badge-yellow">Disabled</span>}
              </div>
              <p className="text-sm text-gray-500">{s.url} &bull; {s.models_count} models &bull; Load {s.current_load}/{s.max_concurrent || 10}</p>
              <p className="text-xs text-gray-600">Latency: {Math.round(s.response_latency_ms)}ms | Errors: {(s.error_rate * 100).toFixed(1)}%</p>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={() => test(s.id)} className="p-2 hover:bg-gray-800 rounded-lg" title="Test"><TestTube size={16} /></button>
              <button onClick={() => toggle(s)} className="p-2 hover:bg-gray-800 rounded-lg" title="Toggle"><Power size={16} /></button>
              <button onClick={() => { setEditing(s); setForm({...s, api_key: ''}); setShowForm(true); }} className="p-2 hover:bg-gray-800 rounded-lg" title="Edit"><Edit2 size={16} /></button>
              <button onClick={() => remove(s.id)} className="p-2 hover:bg-red-900/30 text-red-400 rounded-lg" title="Delete"><Trash2 size={16} /></button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}