import { Routes, Route, NavLink } from 'react-router-dom'
import OrgChart from './pages/OrgChart'
import TaskBoard from './pages/TaskBoard'
import TaskDetail from './pages/TaskDetail'
import Approvals from './pages/Approvals'
import RequirementPool from './pages/RequirementPool'
import RequirementDetail from './pages/RequirementDetail'
import ProjectPolicies from './pages/ProjectPolicies'
import OptimizationSignals from './pages/OptimizationSignals'

const navItems = [
  { to: '/', label: '组织架构' },
  { to: '/requirements', label: '需求池' },
  { to: '/optimization-signals', label: '优化信号' },
  { to: '/project-policies', label: '项目策略' },
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
          <Route path="/requirements" element={<RequirementPool />} />
          <Route path="/requirements/:id" element={<RequirementDetail />} />
          <Route path="/optimization-signals" element={<OptimizationSignals />} />
          <Route path="/project-policies" element={<ProjectPolicies />} />
          <Route path="/tasks" element={<TaskBoard />} />
          <Route path="/tasks/:id" element={<TaskDetail />} />
          <Route path="/approvals" element={<Approvals />} />
        </Routes>
      </main>
    </div>
  )
}
