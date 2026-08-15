import { Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, Server, Brain, MessageSquare, FileText, Settings, LogOut } from 'lucide-react'
import { useAuthStore } from '../store'

const navItems = [
  { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/servers', icon: Server, label: 'Servers' },
  { path: '/models', icon: Brain, label: 'Models' },
  { path: '/playground', icon: MessageSquare, label: 'Playground' },
  { path: '/logs', icon: FileText, label: 'Logs' },
  { path: '/settings', icon: Settings, label: 'Settings' },
]

export default function Layout({ children }) {
  const location = useLocation()
  const logout = useAuthStore((s) => s.logout)
  return (
    <div className="flex h-screen bg-gray-950">
      <aside className="w-64 border-r border-gray-800 bg-gray-900 flex flex-col">
        <div className="p-6 border-b border-gray-800">
          <h1 className="text-xl font-bold text-emerald-400">Hermes Gateway</h1>
          <p className="text-xs text-gray-500 mt-1">Ollama Router</p>
        </div>
        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon
            const active = location.pathname === item.path
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors ${
                  active ? 'bg-emerald-900/30 text-emerald-400' : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
                }`}
              >
                <Icon size={18} />
                {item.label}
              </Link>
            )
          })}
        </nav>
        <div className="p-4 border-t border-gray-800">
          <button onClick={logout} className="flex items-center gap-3 px-4 py-3 text-sm text-gray-400 hover:text-red-400 w-full">
            <LogOut size={18} />
            Logout
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-auto p-8">{children}</main>
    </div>
  )
}