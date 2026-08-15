import { useEffect, useState } from 'react'
import api from '../services/api'

export default function Models() {
  const [models, setModels] = useState([])

  useEffect(() => {
    api.get('/models/cluster').then((res) => setModels(res.data))
  }, [])

  const grouped = models.reduce((acc, m) => {
    if (!acc[m.model_name]) acc[m.model_name] = []
    acc[m.model_name].push(m)
    return acc
  }, {})

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Models</h2>
      <div className="grid grid-cols-1 gap-4">
        {Object.entries(grouped).map(([name, instances]) => (
          <div key={name} className="card">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-lg">{name}</h3>
              <span className="badge badge-green">{instances.length} servers</span>
            </div>
            <div className="grid grid-cols-3 gap-3">
              {instances.map((inst) => (
                <div key={`${inst.server_id}-${name}`} className="bg-gray-800/50 p-3 rounded-lg">
                  <p className="font-medium text-sm">{inst.server_name}</p>
                  <p className="text-xs text-gray-500">{inst.parameter_size} • {inst.quantization}</p>
                  <span className={`badge text-xs mt-2 ${inst.server_healthy ? 'badge-green' : 'badge-red'}`}>
                    {inst.server_healthy ? 'Available' : 'Unavailable'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}