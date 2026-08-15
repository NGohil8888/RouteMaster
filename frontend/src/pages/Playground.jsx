import { useState, useEffect } from 'react'
import api from '../services/api'

export default function Playground() {
  const [servers, setServers] = useState([])
  const [serverId, setServerId] = useState('')
  const [model, setModel] = useState('')
  const [prompt, setPrompt] = useState('')
  const [response, setResponse] = useState('')
  const [loading, setLoading] = useState(false)
  const [stream, setStream] = useState(false)
  const [time, setTime] = useState(0)

  useEffect(() => {
    api.get('/servers/status').then((res) => setServers(res.data.filter((s) => s.is_healthy)))
  }, [])

  const send = async () => {
    setLoading(true)
    setResponse('')
    setTime(0)
    const start = Date.now()
    try {
      if (stream) {
        // SSE streaming
        const res = await fetch('/api/v1/test/prompt', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('hermes_token')}`
          },
          body: JSON.stringify({
            server_id: serverId ? parseInt(serverId) : null,
            model,
            prompt,
            stream: true
          })
        })
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let text = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          text += decoder.decode(value, { stream: true })
          setResponse(text)
        }
        setTime(Date.now() - start)
      } else {
        const res = await api.post('/test/prompt', {
          server_id: serverId ? parseInt(serverId) : null,
          model,
          prompt,
          stream: false
        })
        setResponse(res.data.response)
        setTime(res.data.response_time_ms)
      }
    } catch (err) {
      setResponse(`Error: ${err.response?.data?.detail || err.message}`)
    }
    setLoading(false)
  }

  const clusterTest = async () => {
    setLoading(true)
    setResponse('Running cluster test...\n\n')
    try {
      const res = await api.post('/test/cluster', { model, prompt, stream })
      let text = ''
      for (const r of res.data) {
        text += `--- ${r.server_name} (${r.status}) ---\nTime: ${Math.round(r.response_time_ms)}ms\n${r.response}\n\n`
      }
      setResponse(text)
    } catch (err) {
      setResponse(`Error: ${err.response?.data?.detail || err.message}`)
    }
    setLoading(false)
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Playground</h2>
      <div className="card space-y-4">
        <div className="grid grid-cols-3 gap-4">
          <select className="input" value={serverId} onChange={(e) => setServerId(e.target.value)}>
            <option value="">Auto-select server</option>
            {servers.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          <input className="input" placeholder="Model (e.g. llama3.1)" value={model} onChange={(e) => setModel(e.target.value)} />
          <div className="flex items-center gap-2">
            <input type="checkbox" id="stream" checked={stream} onChange={(e) => setStream(e.target.checked)} />
            <label htmlFor="stream" className="text-sm">Stream</label>
          </div>
        </div>
        <textarea className="input h-32" placeholder="Enter your prompt..." value={prompt} onChange={(e) => setPrompt(e.target.value)} />
        <div className="flex gap-2">
          <button onClick={send} disabled={loading} className="btn-primary">{loading ? 'Sending...' : 'Send'}</button>
          <button onClick={clusterTest} disabled={loading} className="btn-secondary">Cluster Test</button>
        </div>
        {time > 0 && <p className="text-sm text-gray-500">Response time: {Math.round(time)}ms</p>}
        {response && (
          <div className="bg-gray-800/50 p-4 rounded-lg whitespace-pre-wrap text-sm leading-relaxed">
            {response}
          </div>
        )}
      </div>
    </div>
  )
}