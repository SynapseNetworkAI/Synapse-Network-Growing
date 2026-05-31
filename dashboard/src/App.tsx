import { useEffect, useMemo, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
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
import SdkPackageReleaseDetailPage from './pages/SdkPackageReleaseDetailPage'
import SdkReleaseTrainDetailPage from './pages/SdkReleaseTrainDetailPage'
import McpServerReleaseDetailPage from './pages/McpServerReleaseDetailPage'
import PublishingPage from './pages/PublishingPage'
import PublishingTrendResultsPage from './pages/PublishingTrendResultsPage'
import BugsPage from './pages/BugsPage'
import GrowthPage from './pages/GrowthPage'
import ProjectsPage from './pages/ProjectsPage'
import ProjectDetailPage from './pages/ProjectDetailPage'
import ErrorsPage from './pages/ErrorsPage'
import ErrorDetailPage from './pages/ErrorDetailPage'
import { api } from './api'

const primaryNavItems = [
  { to: '/command-center', label: 'Command Center', meta: 'Mission Control' },
  { to: '/planning', label: 'Planning', meta: 'Opportunities & Goals' },
  { to: '/bugs', label: 'Bug List', meta: 'Agent Fix Queue' },
  { to: '/growth', label: 'Growth', meta: 'Acquisition & AI Discovery' },
  { to: '/publishing', label: 'Publishing', meta: 'Social Ops' },
  { to: '/releases', label: 'Releases', meta: 'Delivery' },
  { to: '/schedules', label: 'Schedule', meta: 'Recurring Ops' },
]

const secondaryNavGroups = [
  {
    label: 'Work Queues',
    items: [
      { to: '/gates', label: 'Human Gates', meta: 'Needs operator' },
      { to: '/requirements', label: 'Requirements', meta: 'Engineering queue' },
      { to: '/workflows', label: 'Workflows', meta: 'Runs and definitions' },
      { to: '/intake', label: 'Signals', meta: 'Discovery sources' },
    ],
  },
  {
    label: 'System Ops',
    items: [
      { to: '/system/notifications', label: 'Notifications', meta: 'Lark / queue' },
      { to: '/projects', label: 'Projects', meta: 'Governance' },
      { to: '/errors', label: 'Errors', meta: 'Fingerprints' },
    ],
  },
  {
    label: 'Factory & Knowledge',
    items: [
      { to: '/factory/workflows', label: 'Workflow Factory', meta: 'Read-only specs' },
      { to: '/factory/atoms', label: 'Atom Registry', meta: 'Capability catalog' },
      { to: '/knowledge', label: 'Knowledge', meta: 'Evidence and SOP' },
      { to: '/publishing/trends', label: 'Trend Radar Results', meta: 'X trend search' },
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
  { match: (pathname) => pathname === '/bugs', title: 'Bug List', meta: 'Agent fix queue' },
  { match: (pathname) => pathname === '/growth', title: 'Growth', meta: 'Acquisition and AI discovery' },
  { match: (pathname) => pathname === '/workflows', title: '运行轨迹', meta: 'Workflow runs' },
  { match: (pathname) => pathname.startsWith('/workflows/'), title: '工作流详情', meta: 'State machine detail' },
  { match: (pathname) => pathname === '/schedules', title: '定时任务', meta: 'Scheduled jobs' },
  { match: (pathname) => pathname === '/releases', title: '发布', meta: 'Release list' },
  { match: (pathname) => pathname.startsWith('/releases/mcp-servers/'), title: 'MCP Server 发布', meta: 'MCP registry release' },
  { match: (pathname) => pathname.startsWith('/releases/sdk-packages/'), title: 'SDK Package 发布', meta: 'SDK registry release' },
  { match: (pathname) => pathname.startsWith('/releases/sdk-trains/'), title: 'SDK Release Train', meta: 'SDK package matrix' },
  { match: (pathname) => pathname.startsWith('/releases/'), title: '发布详情', meta: 'Release detail' },
  { match: (pathname) => pathname === '/publishing/trends', title: 'X 趋势雷达结果', meta: 'Social trend radar' },
  { match: (pathname) => pathname === '/publishing', title: '内容发布', meta: 'Social publishing' },
  { match: (pathname) => pathname === '/projects', title: '项目', meta: 'Project list' },
  { match: (pathname) => pathname.startsWith('/projects/'), title: '项目详情', meta: 'Project detail' },
  { match: (pathname) => pathname === '/errors', title: '错误', meta: 'Error list' },
  { match: (pathname) => pathname.startsWith('/errors/'), title: '错误详情', meta: 'Error detail' },
]

function routeTitle(pathname: string) {
  return routeTitles.find((item) => item.match(pathname)) ?? routeTitles[0]
}

function isPrimaryActive(pathname: string, target: string) {
  if (target === '/command-center') return pathname === '/' || pathname === '/command-center'
  return pathname === target || pathname.startsWith(`${target}/`)
}

function topNavClass(isActive: boolean) {
  return [
    'whitespace-nowrap rounded-2xl px-4 py-2 text-sm font-semibold transition',
    isActive
      ? 'border border-cyan-300/25 bg-cyan-300/[0.12] text-cyan-100 shadow-[0_0_28px_rgba(34,211,238,0.10)]'
      : 'border border-transparent text-[color:var(--ops-text-muted)] hover:border-white/10 hover:bg-white/[0.055] hover:text-[color:var(--ops-text-title)]',
  ].join(' ')
}

function CommandSearch({ open, onClose }: Readonly<{ open: boolean; onClose: () => void }>) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/62 px-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="Command search">
      <div className="w-full max-w-3xl overflow-hidden rounded-[28px] border border-white/10 bg-[color:var(--ops-panel)] shadow-[0_28px_120px_rgba(0,0,0,0.55)]">
        <div className="flex items-start justify-between gap-4 border-b border-[color:var(--ops-stroke-soft)] px-6 py-5">
          <div>
            <div className="machine-label text-cyan-200/70">Cmd+K</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-[color:var(--ops-text-title)]">Command Search</h2>
            <p className="mt-2 text-sm text-[color:var(--ops-text-muted)]">低频工具不占主导航；从这里进入 Requirements、Workflows、System Ops 和 Debug surfaces。</p>
          </div>
          <button type="button" className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={onClose}>关闭</button>
        </div>
        <div className="max-h-[66vh] overflow-auto p-5">
          {secondaryNavGroups.map((group) => (
            <section key={group.label} className="mb-5 last:mb-0">
              <div className="machine-label mb-2 px-2 text-[color:var(--ops-text-caption)]">{group.label}</div>
              <div className="grid gap-2 md:grid-cols-2">
                {group.items.map((item) => (
                  <Link key={item.to} to={item.to} className="rounded-2xl border border-white/8 bg-white/[0.035] px-4 py-3 transition hover:border-cyan-300/25 hover:bg-cyan-300/[0.06]" onClick={onClose}>
                    <div className="font-semibold text-[color:var(--ops-text-title)]">{item.label}</div>
                    <div className="mt-1 text-xs text-[color:var(--ops-text-muted)]">{item.meta}</div>
                  </Link>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  )
}

function TopNavigation({ currentMeta }: Readonly<{ currentMeta: string }>) {
  const location = useLocation()
  const [needsHuman, setNeedsHuman] = useState<number | null>(null)
  const [searchOpen, setSearchOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .getWorkflowRunsSummary()
      .then((summary) => {
        if (cancelled || !summary) return
        const count = Number(summary.pending_gate_count ?? summary.needs_human ?? 0)
        setNeedsHuman(Number.isFinite(count) ? count : 0)
      })
      .catch(() => {
        if (!cancelled) setNeedsHuman(null)
      })
    return () => {
      cancelled = true
    }
  }, [location.pathname])

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setSearchOpen(true)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const humanCount = needsHuman ?? 0
  const hasHumanWork = humanCount > 0

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-white/8 bg-[color:var(--ops-header-bg)]/95 px-4 py-3 backdrop-blur-xl md:px-6">
        <div className="mx-auto flex max-w-[1680px] flex-wrap items-center gap-4">
          <Link to="/command-center" className="flex min-w-fit items-center gap-3">
            <span className="inline-flex h-11 w-11 items-center justify-center overflow-hidden rounded-2xl border border-cyan-200/20 bg-white shadow-[0_0_28px_rgba(34,211,238,0.12)]">
              <img src="/synapse-network-icon.svg" alt="SynapseNetwork" className="h-9 w-9" />
            </span>
            <span>
              <span className="machine-label block text-cyan-200/70">Synapse Network</span>
              <span className="block text-lg font-semibold tracking-[-0.04em] text-[color:var(--ops-text-title)]">Agent Ops</span>
            </span>
          </Link>

          <nav className="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto" aria-label="Primary navigation">
            {primaryNavItems.map((item) => (
              <NavLink key={item.to} to={item.to} className={() => topNavClass(isPrimaryActive(location.pathname, item.to))}>
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <Link
              to="/gates"
              className={[
                'rounded-2xl border px-3 py-2 text-sm font-semibold transition',
                hasHumanWork
                  ? 'border-amber-300/35 bg-amber-300/[0.10] text-amber-100'
                  : 'border-white/10 text-[color:var(--ops-text-muted)] hover:bg-white/[0.055]',
              ].join(' ')}
            >
              Needs Human{hasHumanWork ? ` ${humanCount}` : ''}
            </Link>
            <button type="button" className="hidden rounded-2xl border border-white/10 px-3 py-2 text-sm text-[color:var(--ops-text-muted)] transition hover:bg-white/[0.055] md:inline-flex" onClick={() => setSearchOpen(true)}>
              Cmd+K / Search
            </button>
            <Link to="/system/notifications" aria-label="Notifications" className="rounded-2xl border border-white/10 px-3 py-2 text-sm text-[color:var(--ops-text-muted)] transition hover:bg-white/[0.055]">
              Alerts
            </Link>
          </div>

          <div className="hidden w-full border-t border-white/8 pt-2 text-xs text-[color:var(--ops-text-caption)] md:block">
            {currentMeta}
          </div>
        </div>
      </header>
      <CommandSearch open={searchOpen} onClose={() => setSearchOpen(false)} />
    </>
  )
}

export default function App() {
  const location = useLocation()
  const current = routeTitle(location.pathname)
  const routeContext = useMemo(() => `${current.meta} · ${current.title}`, [current.meta, current.title])

  return (
    <div className="min-h-screen bg-[color:var(--ops-bg)] text-[color:var(--ops-text-body)]">
      <div className="min-h-screen">
        <TopNavigation currentMeta={routeContext} />
        <main className="min-h-0 px-4 py-5 md:px-6 md:py-6">
          <div className="mx-auto max-w-[1680px]">
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
              <Route path="/bugs" element={<BugsPage />} />
              <Route path="/growth" element={<GrowthPage />} />
              <Route path="/workflows" element={<WorkflowRunsPage />} />
              <Route path="/workflows/:id" element={<WorkflowRunDetailPage />} />
              <Route path="/schedules" element={<SchedulesPage />} />
              <Route path="/releases" element={<ReleasesPage />} />
              <Route path="/releases/mcp-servers/:id" element={<McpServerReleaseDetailPage />} />
              <Route path="/releases/sdk-packages/:id" element={<SdkPackageReleaseDetailPage />} />
              <Route path="/releases/sdk-trains/:version" element={<SdkReleaseTrainDetailPage />} />
              <Route path="/releases/:requirementId" element={<ReleaseDetailPage />} />
              <Route path="/publishing" element={<PublishingPage />} />
              <Route path="/publishing/trends" element={<PublishingTrendResultsPage />} />
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
  )
}
