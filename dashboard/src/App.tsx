import { Routes, Route, NavLink } from 'react-router-dom'
import OrgChart from './pages/OrgChart'
import TaskBoard from './pages/TaskBoard'
import Approvals from './pages/Approvals'

const navItems = [
  { to: '/', label: '组织架构' },
  { to: '/tasks', label: '任务看板' },
  { to: '/approvals', label: '审批中心' },
]

export default function App() {
  return (
    <div className="min-h-screen">
      <nav className="bg-white border-b px-6 py-3 flex items-center gap-6">
        <span className="font-bold text-lg mr-4">Synapse Ops</span>
        {navItems.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            className={({ isActive }) =>
              `text-sm px-3 py-1 rounded ${isActive ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-100'}`
            }
          >
            {n.label}
          </NavLink>
        ))}
      </nav>
      <main className="max-w-6xl mx-auto p-6">
        <Routes>
          <Route path="/" element={<OrgChart />} />
          <Route path="/tasks" element={<TaskBoard />} />
          <Route path="/approvals" element={<Approvals />} />
        </Routes>
      </main>
    </div>
  )
}
