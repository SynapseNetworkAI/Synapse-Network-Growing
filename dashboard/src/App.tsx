import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import CommandCenterPage from './pages/CommandCenterPage'
import RequirementPool from './pages/RequirementPool'
import RequirementDetail from './pages/RequirementDetail'
import WorkflowRunsPage from './pages/WorkflowRunsPage'
import WorkflowRunDetailPage from './pages/WorkflowRunDetailPage'
import PlanningPage from './pages/PlanningPage'
import HumanGatesPage from './pages/HumanGatesPage'
import WorkflowDefinitionsPage from './pages/WorkflowDefinitionsPage'
import AtomRegistryPage from './pages/AtomRegistryPage'
import IntakePage from './pages/IntakePage'
import KnowledgePage from './pages/KnowledgePage'
import NotificationsPage from './pages/NotificationsPage'
import SchedulesPage from './pages/SchedulesPage'
import ReleasesPage from './pages/ReleasesPage'
import ReleaseDetailPage from './pages/ReleaseDetailPage'
import PublishingPage from './pages/PublishingPage'
import ProjectsPage from './pages/ProjectsPage'
import ProjectDetailPage from './pages/ProjectDetailPage'
import ErrorsPage from './pages/ErrorsPage'
import ErrorDetailPage from './pages/ErrorDetailPage'

const navGroups = [
  {
    label: 'Strategy',
    items: [
      { to: '/command-center', label: '司令部', meta: 'Mission Control' },
      { to: '/planning', label: '经营规划', meta: 'Operating Manifest' },
    ],
  },
  {
    label: 'Intervention',
    items: [
      { to: '/gates', label: '门禁审批', meta: 'Human Oracle' },
      { to: '/intake', label: '信号入口', meta: 'Requirement Discovery' },
    ],
  },
  {
    label: 'Execution',
    items: [
      { to: '/requirements', label: '需求池', meta: 'Requirements' },
      { to: '/workflows', label: '运行轨迹', meta: 'Workflow Runs' },
      { to: '/releases', label: '发布交付', meta: 'Delivery' },
      { to: '/publishing', label: '内容发布', meta: 'Social Publishing' },
    ],
  },
  {
    label: 'Factory',
    items: [
      { to: '/factory/workflows', label: '状态机定义', meta: 'Workflow Specs' },
      { to: '/factory/atoms', label: '原子能力库', meta: 'Atom Registry' },
      { to: '/knowledge', label: '知识资产', meta: 'SOP Ledger' },
    ],
  },
  {
    label: 'System Ops',
    items: [
      { to: '/schedules', label: '定时任务', meta: 'Scheduled Jobs' },
      { to: '/system/notifications', label: '通知队列', meta: 'Lark / Queue' },
      { to: '/projects', label: '项目治理', meta: 'Projects' },
      { to: '/errors', label: '错误指纹', meta: 'Error Signals' },
    ],
  },
]

const routeTitles: Array<{ match: (pathname: string) => boolean; title: string; meta: string }> = [
  { match: (pathname) => pathname === '/' || pathname === '/command-center', title: '司令部', meta: 'Command center' },
  { match: (pathname) => pathname === '/intake', title: '信号入口', meta: 'Requirement discovery' },
  { match: (pathname) => pathname === '/gates', title: '门禁审批', meta: 'Human oracle' },
  { match: (pathname) => pathname === '/factory/workflows', title: '状态机定义', meta: 'Workflow factory' },
  { match: (pathname) => pathname === '/factory/atoms', title: '原子能力库', meta: 'Atom registry' },
  { match: (pathname) => pathname === '/knowledge', title: '知识资产', meta: 'Artifacts and SOP' },
  { match: (pathname) => pathname === '/system/notifications', title: '通知队列', meta: 'Notification dispatcher' },
  { match: (pathname) => pathname === '/requirements', title: '需求池', meta: 'Requirement list' },
  { match: (pathname) => pathname.startsWith('/requirements/'), title: '需求详情', meta: 'Requirement detail' },
  { match: (pathname) => pathname === '/planning', title: '经营规划', meta: 'Planning control plane' },
  { match: (pathname) => pathname === '/workflows', title: '运行轨迹', meta: 'Workflow runs' },
  { match: (pathname) => pathname.startsWith('/workflows/'), title: '工作流详情', meta: 'State machine detail' },
  { match: (pathname) => pathname === '/schedules', title: '定时任务', meta: 'Scheduled jobs' },
  { match: (pathname) => pathname === '/releases', title: '发布', meta: 'Release list' },
  { match: (pathname) => pathname.startsWith('/releases/'), title: '发布详情', meta: 'Release detail' },
  { match: (pathname) => pathname === '/publishing', title: '内容发布', meta: 'Social publishing' },
  { match: (pathname) => pathname === '/projects', title: '项目', meta: 'Project list' },
  { match: (pathname) => pathname.startsWith('/projects/'), title: '项目详情', meta: 'Project detail' },
  { match: (pathname) => pathname === '/errors', title: '错误', meta: 'Error list' },
  { match: (pathname) => pathname.startsWith('/errors/'), title: '错误详情', meta: 'Error detail' },
]

function routeTitle(pathname: string) {
  return routeTitles.find((item) => item.match(pathname)) ?? routeTitles[0]
}

function allNavItems() {
  return navGroups.flatMap((group) => group.items)
}

export default function App() {
  const location = useLocation()
  const current = routeTitle(location.pathname)

  return (
    <div className="min-h-screen bg-[color:var(--ops-bg)] text-[color:var(--ops-text-body)]">
      <div className="flex min-h-screen">
        <aside className="hidden w-[286px] shrink-0 border-r border-white/8 bg-[color:var(--ops-sidebar-bg)] px-5 py-6 lg:flex lg:flex-col">
          <div>
            <div className="flex items-center gap-3">
              <span className="inline-flex h-12 w-12 items-center justify-center overflow-hidden rounded-2xl border border-cyan-200/20 bg-white shadow-[0_0_28px_rgba(34,211,238,0.12)]">
                <img src="/synapse-network-icon.svg" alt="SynapseNetwork" className="h-10 w-10" />
              </span>
              <div>
                <div className="machine-label text-cyan-200/70">Synapse Network</div>
                <div className="mt-1 text-2xl font-semibold tracking-[-0.04em] text-[color:var(--ops-text-title)]">Agent Ops</div>
              </div>
            </div>
            <div className="mt-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">Human-Agent Control Plane</div>
          </div>

          <nav className="mt-8 space-y-6">
            {navGroups.map((group) => (
              <div key={group.label}>
                <div className="machine-label mb-2 px-3 text-[color:var(--ops-text-caption)]">{group.label}</div>
                <div className="space-y-1">
                  {group.items.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      className={({ isActive }) =>
                        [
                          'group flex items-center justify-between rounded-xl px-3 py-2.5 text-sm font-medium transition',
                          isActive
                            ? 'border border-cyan-300/20 bg-cyan-300/12 text-cyan-100 shadow-[0_0_28px_rgba(34,211,238,0.08)]'
                            : 'border border-transparent text-[color:var(--ops-text-muted)] hover:border-white/8 hover:bg-white/[0.045] hover:text-[color:var(--ops-text-title)]',
                        ].join(' ')
                      }
                    >
                      <span>{item.label}</span>
                      <span className="hidden font-mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--ops-text-caption)] xl:inline">{item.meta}</span>
                    </NavLink>
                  ))}
                </div>
              </div>
            ))}
          </nav>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="border-b border-white/8 bg-[color:var(--ops-header-bg)] px-4 py-4 backdrop-blur md:px-6">
            <div className="flex items-center justify-between gap-4">
              <div>
                <div className="machine-label text-[color:var(--ops-text-caption)]">{current.meta}</div>
                <h1 className="mt-1 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">{current.title}</h1>
              </div>
              <div className="flex max-w-[68vw] items-center gap-2 overflow-x-auto lg:hidden">
                {allNavItems().map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      [
                        'whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition',
                        isActive
                          ? 'bg-cyan-300/12 text-cyan-100'
                          : 'text-[color:var(--ops-text-muted)] hover:bg-white/[0.06]',
                      ].join(' ')
                    }
                  >
                    {item.label}
                  </NavLink>
                ))}
              </div>
            </div>
          </header>

          <main className="min-h-0 flex-1 px-4 py-5 md:px-6 md:py-6">
            <div className="mx-auto max-w-[1480px]">
              <Routes>
                <Route path="/" element={<Navigate to="/command-center" replace />} />
                <Route path="/command-center" element={<CommandCenterPage />} />
                <Route path="/intake" element={<IntakePage />} />
                <Route path="/gates" element={<HumanGatesPage />} />
                <Route path="/factory/workflows" element={<WorkflowDefinitionsPage />} />
                <Route path="/factory/atoms" element={<AtomRegistryPage />} />
                <Route path="/knowledge" element={<KnowledgePage />} />
                <Route path="/system/notifications" element={<NotificationsPage />} />
                <Route path="/requirements" element={<RequirementPool />} />
                <Route path="/requirements/:id" element={<RequirementDetail />} />
                <Route path="/planning" element={<PlanningPage />} />
                <Route path="/workflows" element={<WorkflowRunsPage />} />
                <Route path="/workflows/:id" element={<WorkflowRunDetailPage />} />
                <Route path="/schedules" element={<SchedulesPage />} />
                <Route path="/releases" element={<ReleasesPage />} />
                <Route path="/releases/:requirementId" element={<ReleaseDetailPage />} />
                <Route path="/publishing" element={<PublishingPage />} />
                <Route path="/projects" element={<ProjectsPage />} />
                <Route path="/projects/:id" element={<ProjectDetailPage />} />
                <Route path="/errors" element={<ErrorsPage />} />
                <Route path="/errors/:fingerprintKey" element={<ErrorDetailPage />} />
                <Route path="*" element={<Navigate to="/command-center" replace />} />
              </Routes>
            </div>
          </main>
        </div>
      </div>
    </div>
  )
}
