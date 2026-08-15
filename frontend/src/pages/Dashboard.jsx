import { useEffect } from 'react'
import { useAppStore } from '../store'
import api from '../services/api'
import { Server, Activity, Clock, AlertTriangle } from 'lucide-react'

export default function Dashboard() {
  const { stats, setStats, servers, setServers } = useAppStore()

  useEffect(() => {
    const load = async () => {
      const [s, st] = await Promise.all([
        api.get('/servers/status'),
        api.get('/dashboard/stats')
      ])
      setServers(s.data)
      setStats(st.data)
    }
    load()
    const interval = setInterval(load, 5000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Dashboard</h2>
      <div className="grid grid-cols-4 gap-4">
        <StatCard icon={Server} label="Servers" value={`${stats?.online_servers || 0}/${stats?.total_servers || 0}`} sub="Online" color="text-emerald-400" />
        <StatCard icon={Activity} label="Active Requests" value={stats?.active_requests || 0} sub="Processing" color="text-blue-400" />
        <StatCard icon={Clock} label="Avg Latency" value={`${Math.round(stats?.avg_latency_ms || 0)}ms`} sub="Last 5 min" color="text-amber-400" />
        <StatCard icon={AlertTriangle} label="Error Rate" value={`${((stats?.error_rate || 0) * 100).toFixed(1)}%`} sub="Last 5 min" color="text-red-400" />
      </div>
      <div className="grid grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-lg font-semibold mb-4">Server Status</h3>
          <div className="space-y-3">
            {servers.map((s) => (
              <div key={s.id} className="flex items-center justify-between p-3 bg-gray-800/50 rounded-lg">
                <div>
                  <p className="font-medium">{s.name}</p>
                  <p className="text-xs text-gray-500">{s.url}</p>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-xs text-gray-400">{s.current_load}/{s.max_concurrent || 10} load</span>
                  <span className={`badge ${s.is_healthy ? 'badge-green' : 'badge-red'}`}>
                    {s.is_healthy ? 'Healthy' : 'Unhealthy'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="card">
          <h3 className="text-lg font-semibold mb-4">Overview</h3>
          <div className="space-y-4">
            <div className="flex justify-between p-3 bg-gray-800/50 rounded-lg">
              <span className="text-gray-400">Total Models</span>
              <span className="font-semibold">{stats?.total_models || 0}</span>
            </div>
            <div className="flex justify-between p-3 bg-gray-800/50 rounded-lg">
              <span className="text-gray-400">Requests/min</span>
              <span className="font-semibold">{stats?.requests_per_minute || 0}</span>
            </div>
            <div className="flex justify-between p-3 bg-gray-800/50 rounded-lg">
              <span className="text-gray-400">Offline Servers</span>
              <span className="font-semibold text-red-400">{stats?.offline_servers || 0}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function StatCard({ icon: Icon, label, value, sub, color }) {
  return (
    <div className="card">
      <div className="flex items-center gap-3 mb-3">
        <Icon size={20} className={color} />
        <span className="text-sm text-gray-400">{label}</span>
      </div>
      <p className="text-3xl font-bold">{value}</p>
      <p className="text-xs text-gray-500 mt-1">{sub}</p>
    </div>
  )
}