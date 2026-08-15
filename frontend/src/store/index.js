import { create } from 'zustand'

export const useAuthStore = create((set) => ({
  token: localStorage.getItem('hermes_token') || null,
  user: null,
  setToken: (token) => {
    localStorage.setItem('hermes_token', token)
    set({ token })
  },
  logout: () => {
    localStorage.removeItem('hermes_token')
    set({ token: null, user: null })
  }
}))

export const useAppStore = create((set) => ({
  stats: null,
  servers: [],
  models: [],
  routingMode: 'AUTO',
  setStats: (stats) => set({ stats }),
  setServers: (servers) => set({ servers }),
  setModels: (models) => set({ models }),
  setRoutingMode: (mode) => set({ routingMode: mode })
}))