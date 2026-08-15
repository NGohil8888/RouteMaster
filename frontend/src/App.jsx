import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Servers from './pages/Servers'
import Models from './pages/Models'
import Playground from './pages/Playground'
import Logs from './pages/Logs'
import Settings from './pages/Settings'
import Login from './pages/Login'
import { useAuthStore } from './store'

function App() {
  const token = useAuthStore((s) => s.token)
  if (!token) return <Login />
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/servers" element={<Servers />} />
        <Route path="/models" element={<Models />} />
        <Route path="/playground" element={<Playground />} />
        <Route path="/logs" element={<Logs />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </Layout>
  )
}

export default App