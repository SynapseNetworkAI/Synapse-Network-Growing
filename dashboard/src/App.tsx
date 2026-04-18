import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import RequirementPool from './pages/RequirementPool'
import RequirementDetail from './pages/RequirementDetail'
import WorkflowRunsPage from './pages/WorkflowRunsPage'
import WorkflowRunDetailPage from './pages/WorkflowRunDetailPage'
import ReleasesPage from './pages/ReleasesPage'
import ReleaseDetailPage from './pages/ReleaseDetailPage'
import ProjectsPage from './pages/ProjectsPage'
import ProjectDetailPage from './pages/ProjectDetailPage'
import ErrorsPage from './pages/ErrorsPage'
import ErrorDetailPage from './pages/ErrorDetailPage'

const primaryNav = [
  { to: '/requirements', label: '需求' },
  { to: '/workflows', label: '工作流' },
  { to: '/releases', label: '发布' },
  { to: '/projects', label: '项目' },
  { to: '/errors', label: '错误' },
]

const routeTitles: Array<{ match: (pathname: string) => boolean; title: string; meta: string }> = [
  { match: (pathname) => pathname === '/' || pathname === '/requirements', title: '需求', meta: 'Requirement list' },
  { match: (pathname) => pathname.startsWith('/requirements/'), title: '需求详情', meta: 'Requirement detail' },
  { match: (pathname) => pathname === '/workflows', title: '工作流', meta: 'Workflow runs' },
  { match: (pathname) => pathname.startsWith('/workflows/'), title: '工作流详情', meta: 'State machine detail' },
  { match: (pathname) => pathname === '/releases', title: '发布', meta: 'Release list' },
  { match: (pathname) => pathname.startsWith('/releases/'), title: '发布详情', meta: 'Release detail' },
  { match: (pathname) => pathname === '/projects', title: '项目', meta: 'Project list' },
  { match: (pathname) => pathname.startsWith('/projects/'), title: '项目详情', meta: 'Project detail' },
  { match: (pathname) => pathname === '/errors', title: '错误', meta: 'Error list' },
  { match: (pathname) => pathname.startsWith('/errors/'), title: '错误详情', meta: 'Error detail' },
]

function routeTitle(pathname: string) {
  return routeTitles.find((item) => item.match(pathname)) ?? routeTitles[0]
}

export default function App() {
  const location = useLocation()
  const current = routeTitle(location.pathname)

  return (
    <div className="min-h-screen bg-[color:var(--ops-bg)] text-[color:var(--ops-text-body)]">
      <div className="flex min-h-screen">
        <aside className="hidden w-[260px] shrink-0 border-r border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-sidebar-bg)] px-5 py-6 lg:flex lg:flex-col">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-[color:var(--ops-text-caption)]">Synapse Network</div>
            <div className="mt-3 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">Agent Ops</div>
          </div>

          <nav className="mt-8 space-y-1">
            {primaryNav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  [
                    'flex items-center rounded-xl px-3 py-2.5 text-sm font-medium transition',
                    isActive
                      ? 'bg-[color:var(--ops-accent-soft)] text-[color:var(--ops-accent-strong)]'
                      : 'text-[color:var(--ops-text-muted)] hover:bg-white hover:text-[color:var(--ops-text-title)]',
                  ].join(' ')
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="border-b border-[color:var(--ops-stroke-soft)] bg-white/88 px-4 py-4 backdrop-blur md:px-6">
            <div className="flex items-center justify-between gap-4">
              <div>
                <div className="text-[11px] uppercase tracking-[0.24em] text-[color:var(--ops-text-caption)]">{current.meta}</div>
                <h1 className="mt-1 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">{current.title}</h1>
              </div>
              <div className="flex items-center gap-2 lg:hidden">
                {primaryNav.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      [
                        'rounded-lg px-3 py-2 text-sm font-medium transition',
                        isActive
                          ? 'bg-[color:var(--ops-accent-soft)] text-[color:var(--ops-accent-strong)]'
                          : 'text-[color:var(--ops-text-muted)] hover:bg-white',
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
                <Route path="/" element={<Navigate to="/requirements" replace />} />
                <Route path="/requirements" element={<RequirementPool />} />
                <Route path="/requirements/:id" element={<RequirementDetail />} />
                <Route path="/workflows" element={<WorkflowRunsPage />} />
                <Route path="/workflows/:id" element={<WorkflowRunDetailPage />} />
                <Route path="/releases" element={<ReleasesPage />} />
                <Route path="/releases/:requirementId" element={<ReleaseDetailPage />} />
                <Route path="/projects" element={<ProjectsPage />} />
                <Route path="/projects/:id" element={<ProjectDetailPage />} />
                <Route path="/errors" element={<ErrorsPage />} />
                <Route path="/errors/:fingerprintKey" element={<ErrorDetailPage />} />
                <Route path="*" element={<Navigate to="/requirements" replace />} />
              </Routes>
            </div>
          </main>
        </div>
      </div>
    </div>
  )
}
