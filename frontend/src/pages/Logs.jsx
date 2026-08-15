import { useEffect, useState } from 'react'
import api from '../services/api'

export default function Logs() {
  const [logs, setLogs] = useState([])
  const [filter, setFilter] = useState({ server_id: '', model: '', status: '', minutes: 60 })

  const load = async () => {
    const params = {}
    if (filter.server_id) params.server_id = filter.server_id
    if (filter.model) params.model = filter.model
    if (filter.status) params.status = filter.status
    params.minutes = filter.minutes
    const res = await api.get('/logs', { params })
    setLogs(res.data)
  }

  useEffect(() => { load() }, [filter])

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Request Logs</h2>
      <div className="flex gap-3">
        <input className="input w-48" placeholder="Model" value={filter.model} onChange={(e) => setFilter({...filter, model: e.target.value})} />
        <select className="input w-40" value={filter.status} onChange={(e) => setFilter({...filter, status: e.target.value})}>
          <option value="">All Status</option>
          <option value="success">Success</option>
          <option value="error">Error</option>
        </select>
        <select className="input w-40" value={filter.minutes} onChange={(e) => setFilter({...filter, minutes: parseInt(e.target.value)})}>
          <option value={60}>Last Hour</option>
          <option value={360}>Last 6 Hours</option>
          <option value={1440}>Last 24 Hours</option>
        </select>
      </div>
      <div className="card overflow-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-800">
              <th className="pb-3">Time</th>
              <th className="pb-3">Request ID</th>
              <th className="pb-3">Model</th>
              <th className="pb-3">Server</th>
              <th className="pb-3">Mode</th>
              <th className="pb-3">Latency</th>
              <th className="pb-3">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {logs.map((log) => (
              <tr key={log.id} className="text-gray-300">
                <td className="py-3">{new Date(log.timestamp).toLocaleTimeString()}</td>
                <td className="py-3 font-mono text-xs">{log.request_id.slice(0, 8)}</td>
                <td className="py-3">{log.model}</td>
                <td className="py-3">{log.server_name || 'Unknown'}</td>
                <td className="py-3">{log.routing_mode}</td>
                <td className="py-3">{Math.round(log.response_time_ms)}ms</td>
                <td className="py-3">
                  <span className={`badge ${log.status === 'success' ? 'badge-green' : 'badge-red'}`}>{log.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}