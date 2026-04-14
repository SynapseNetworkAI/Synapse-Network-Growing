import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import RequirementPool from './pages/RequirementPool'
import RequirementDetail from './pages/RequirementDetail'
import ExecutionsPage from './pages/ExecutionsPage'
import ExecutionDetailPage from './pages/ExecutionDetailPage'
import ReleasesPage from './pages/ReleasesPage'
import ReleaseDetailPage from './pages/ReleaseDetailPage'
import ErrorsPage from './pages/ErrorsPage'
import ErrorDetailPage from './pages/ErrorDetailPage'

const navItems = [
  { to: '/requirements', label: '需求' },
  { to: '/executions', label: '执行' },
  { to: '/releases', label: '发布' },
]

const utilityNavItems = [
  { to: '/errors', label: '错误日志' },
]

const routeBriefs = [
  {
    match: (pathname: string) => pathname === '/requirements' || pathname === '/',
    eyebrow: 'Requirement Surface',
    title: '需求面',
    description: '只管理为什么做、要做到什么、作用在哪个项目。执行与发布跳转到各自独立页面。',
    chips: ['intent', 'acceptance', 'priority'],
  },
  {
    match: (pathname: string) => pathname.startsWith('/requirements/'),
    eyebrow: 'Requirement Detail',
    title: '需求详情',
    description: '查看单条 requirement 的业务意图、验收标准和策略摘要，不混入执行控制或发布操作。',
    chips: ['intent', 'policy', 'handoff'],
  },
  {
    match: (pathname: string) => pathname === '/executions',
    eyebrow: 'Execution Console',
    title: '执行面',
    description: '聚焦 agent 执行图、运行时、验证结果和事件恢复，让模型在最小治理下完成工作。',
    chips: ['execute', 'validate', 'incident'],
  },
  {
    match: (pathname: string) => pathname.startsWith('/executions/'),
    eyebrow: 'Execution Detail',
    title: '执行详情',
    description: '按单次 execution run 查看节点进展、任务证据、验证结果和恢复动作。',
    chips: ['nodes', 'runtime', 'validation'],
  },
  {
    match: (pathname: string) => pathname === '/releases',
    eyebrow: 'Release Center',
    title: '发布面',
    description: '集中处理 release candidate、分支准备、PR、staging / production promotion 与 rollback。',
    chips: ['release', 'deploy', 'rollback'],
  },
  {
    match: (pathname: string) => pathname.startsWith('/releases/'),
    eyebrow: 'Release Detail',
    title: '发布详情',
    description: '查看单条 requirement 的 release record、PR、部署历史与 promotion 动作。',
    chips: ['branch', 'pr', 'deployment'],
  },
  {
    match: (pathname: string) => pathname === '/errors',
    eyebrow: 'Stability Console',
    title: '错误日志',
    description: '辅助治理页，聚合高信号错误、关联 requirement 与执行状态，不替代三大主业务面。',
    chips: ['errors', 'fingerprints', 'alerts'],
  },
  {
    match: (pathname: string) => pathname.startsWith('/errors/'),
    eyebrow: 'Error Fingerprint',
    title: '错误详情',
    description: '查看单个 error fingerprint 的事件证据、关联 requirement / execution 和通知历史。',
    chips: ['evidence', 'requirement', 'notifications'],
  },
]

function getRouteBrief(pathname: string) {
  return routeBriefs.find((item) => item.match(pathname)) ?? routeBriefs[0]
}

export default function App() {
  const location = useLocation()
  const brief = getRouteBrief(location.pathname)

  return (
    <div className="min-h-screen text-[color:var(--ops-text-body)]">
      <div className="mx-auto flex min-h-screen max-w-[var(--ops-page-max)] gap-[var(--ops-content-gutter)] px-3 py-3 md:px-5 md:py-5">
        <aside className="hidden w-[var(--ops-sidebar-width)] shrink-0 flex-col rounded-[var(--ops-radius-shell)] border border-white/8 bg-[color:var(--ops-shell-bg)] px-5 py-5 text-[color:var(--ops-text-on-dark)] shadow-[0_28px_90px_rgba(15,23,42,0.28)] lg:flex">
          <div className="rounded-[24px] border border-white/10 bg-white/5 p-4">
            <div className="text-[11px] uppercase tracking-[0.24em] text-sky-200/80">Synapse Network Growing</div>
            <div className="mt-3 text-2xl font-semibold tracking-tight">Agent-First Ops</div>
            <p className="mt-2 text-sm leading-6 text-slate-300/92">
              程序只做 intake、执行编排、validate 和 release 记录，不替 agent 决定执行内容。
            </p>
          </div>

          <div className="mt-6 text-[11px] uppercase tracking-[0.22em] text-slate-400">Surfaces</div>
          <nav className="mt-3 space-y-1.5 border-y border-white/8 py-4">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `block rounded-2xl px-4 py-3 text-sm transition ${
                    isActive
                      ? 'bg-[linear-gradient(135deg,rgba(71,102,255,0.96),rgba(46,164,255,0.82))] text-white shadow-[0_12px_28px_rgba(59,130,246,0.22)]'
                      : 'text-slate-300 hover:bg-white/6 hover:text-white'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="mt-4 text-[11px] uppercase tracking-[0.22em] text-slate-400">Stability</div>
          <nav className="mt-3 space-y-1.5">
            {utilityNavItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `block rounded-2xl px-4 py-3 text-sm transition ${
                    isActive
                      ? 'bg-white/10 text-white shadow-[0_10px_24px_rgba(15,23,42,0.18)]'
                      : 'text-slate-300 hover:bg-white/6 hover:text-white'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="mt-auto rounded-[24px] border border-white/10 bg-white/5 p-4">
            <div className="text-[11px] uppercase tracking-[0.22em] text-slate-400">Governance</div>
            <div className="mt-2 text-sm font-medium text-white">需求治理 · 稳定性治理 · 发布治理</div>
            <p className="mt-2 text-xs leading-5 text-slate-300">
              simple task 默认直接进入 execute；复杂任务只在 execution 面展开节点图。
            </p>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <div className="ops-shell overflow-x-auto rounded-[var(--ops-radius-shell)] px-3 py-2 lg:hidden">
            <div className="flex min-w-max items-center gap-2">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `rounded-xl px-3 py-2 text-sm transition ${
                      isActive ? 'bg-[color:var(--ops-shell-bg)] text-white' : 'text-[color:var(--ops-text-muted)] hover:bg-white/70'
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
              {utilityNavItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `rounded-xl px-3 py-2 text-sm transition ${
                      isActive ? 'bg-white/70 text-[color:var(--ops-text-title)]' : 'text-[color:var(--ops-text-muted)] hover:bg-white/70'
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          </div>

          <header className="ops-shell rounded-[var(--ops-radius-shell)] px-5 py-5 md:px-7 md:py-6">
            <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
              <div className="max-w-3xl">
                <div className="text-[11px] uppercase tracking-[0.28em] text-[color:var(--ops-text-caption)]">{brief.eyebrow}</div>
                <h1 className="mt-3 text-3xl font-semibold tracking-tight text-[color:var(--ops-text-title)] md:text-[2.4rem]">{brief.title}</h1>
                <p className="mt-3 max-w-2xl text-sm leading-7 text-[color:var(--ops-text-muted)] md:text-[15px]">{brief.description}</p>
              </div>
              <div className="grid gap-0 overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white/78 sm:grid-cols-3 xl:w-[420px]">
                {brief.chips.map((chip, index) => (
                  <div
                    key={chip}
                    className={`border-l px-4 py-3 text-sm first:border-l-0 ${
                      index === 0
                        ? 'border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] text-[color:var(--ops-state-running-text)]'
                        : index === 1
                          ? 'border-[color:var(--ops-state-ready-border)] bg-[color:var(--ops-state-ready-bg)] text-[color:var(--ops-state-ready-text)]'
                          : 'border-[color:var(--ops-state-validating-border)] bg-[color:var(--ops-state-validating-bg)] text-[color:var(--ops-state-validating-text)]'
                    }`}
                  >
                    <div className="text-[11px] uppercase tracking-[0.22em] opacity-60">Focus</div>
                    <div className="mt-1 font-medium">{chip}</div>
                  </div>
                ))}
              </div>
            </div>
          </header>

          <main className="ops-shell min-h-[calc(100vh-8rem)] rounded-[var(--ops-radius-shell)] p-4 md:p-6">
            <Routes>
              <Route path="/" element={<Navigate to="/requirements" replace />} />
              <Route path="/requirements" element={<RequirementPool />} />
              <Route path="/requirements/:id" element={<RequirementDetail />} />
              <Route path="/executions" element={<ExecutionsPage />} />
              <Route path="/executions/:id" element={<ExecutionDetailPage />} />
              <Route path="/releases" element={<ReleasesPage />} />
              <Route path="/releases/:requirementId" element={<ReleaseDetailPage />} />
              <Route path="/errors" element={<ErrorsPage />} />
              <Route path="/errors/:fingerprintKey" element={<ErrorDetailPage />} />
              <Route path="*" element={<Navigate to="/requirements" replace />} />
            </Routes>
          </main>
        </div>
      </div>
    </div>
  )
}
