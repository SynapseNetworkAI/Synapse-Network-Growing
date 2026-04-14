import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import RequirementPool from './pages/RequirementPool'
import RequirementDetail from './pages/RequirementDetail'
import ExecutionsPage from './pages/ExecutionsPage'
import ExecutionDetailPage from './pages/ExecutionDetailPage'
import ReleasesPage from './pages/ReleasesPage'
import ReleaseDetailPage from './pages/ReleaseDetailPage'

const navItems = [
  { to: '/requirements', label: '需求' },
  { to: '/executions', label: '执行' },
  { to: '/releases', label: '发布' },
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
]

function getRouteBrief(pathname: string) {
  return routeBriefs.find((item) => item.match(pathname)) ?? routeBriefs[0]
}

export default function App() {
  const location = useLocation()
  const brief = getRouteBrief(location.pathname)

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.14),_transparent_28%),radial-gradient(circle_at_bottom_right,_rgba(16,185,129,0.12),_transparent_24%),linear-gradient(180deg,_#f8fafc_0%,_#eef2f7_100%)] text-slate-900">
      <div className="mx-auto flex min-h-screen max-w-[1500px] gap-4 px-3 py-3 md:px-5 md:py-5">
        <aside className="hidden w-[270px] shrink-0 flex-col rounded-[30px] border border-white/70 bg-[rgba(10,18,36,0.94)] px-5 py-5 text-slate-100 shadow-[0_24px_80px_rgba(15,23,42,0.24)] lg:flex">
          <div className="rounded-[24px] border border-white/10 bg-white/5 p-4">
            <div className="text-[11px] uppercase tracking-[0.24em] text-sky-200/80">Synapse Network Growing</div>
            <div className="mt-3 text-2xl font-semibold tracking-tight">Agent-First Ops</div>
            <p className="mt-2 text-sm leading-6 text-slate-300">
              程序只做 intake、执行编排、validate 和 release 记录，不替 agent 决定执行内容。
            </p>
          </div>

          <div className="mt-5 text-[11px] uppercase tracking-[0.22em] text-slate-400">Surfaces</div>
          <nav className="mt-3 space-y-1.5">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `block rounded-2xl px-4 py-3 text-sm transition ${
                    isActive
                      ? 'bg-[linear-gradient(135deg,rgba(91,124,250,0.96),rgba(48,180,255,0.92))] text-white shadow-[0_16px_32px_rgba(59,130,246,0.25)]'
                      : 'text-slate-300 hover:bg-white/6 hover:text-white'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="mt-auto rounded-[24px] border border-white/10 bg-white/5 p-4">
            <div className="text-[11px] uppercase tracking-[0.22em] text-slate-400">Core Flow</div>
            <div className="mt-2 text-sm font-medium text-white">intake - execute - validate - deliver</div>
            <p className="mt-2 text-xs leading-5 text-slate-300">
              simple task 默认直接进入 execute；复杂任务只在 execution 面展开节点图。
            </p>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <div className="overflow-x-auto rounded-[26px] border border-white/80 bg-white/70 px-3 py-2 shadow-[0_12px_44px_rgba(148,163,184,0.14)] backdrop-blur lg:hidden">
            <div className="flex min-w-max items-center gap-2">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `rounded-xl px-3 py-2 text-sm transition ${
                      isActive ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          </div>

          <header className="rounded-[30px] border border-white/80 bg-white/72 px-5 py-5 shadow-[0_18px_60px_rgba(148,163,184,0.16)] backdrop-blur md:px-7 md:py-6">
            <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
              <div className="max-w-3xl">
                <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">{brief.eyebrow}</div>
                <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 md:text-[2.35rem]">{brief.title}</h1>
                <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-600 md:text-[15px]">{brief.description}</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-3 xl:w-[420px]">
                {brief.chips.map((chip, index) => (
                  <div
                    key={chip}
                    className={`rounded-2xl border px-4 py-3 text-sm ${
                      index === 0
                        ? 'border-sky-200 bg-sky-50 text-sky-900'
                        : index === 1
                          ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
                          : 'border-amber-200 bg-amber-50 text-amber-900'
                    }`}
                  >
                    <div className="text-[11px] uppercase tracking-[0.22em] opacity-60">Focus</div>
                    <div className="mt-1 font-medium">{chip}</div>
                  </div>
                ))}
              </div>
            </div>
          </header>

          <main className="min-h-[calc(100vh-8rem)] rounded-[30px] border border-white/80 bg-white/66 p-4 shadow-[0_20px_64px_rgba(148,163,184,0.18)] backdrop-blur md:p-6">
            <Routes>
              <Route path="/" element={<Navigate to="/requirements" replace />} />
              <Route path="/requirements" element={<RequirementPool />} />
              <Route path="/requirements/:id" element={<RequirementDetail />} />
              <Route path="/executions" element={<ExecutionsPage />} />
              <Route path="/executions/:id" element={<ExecutionDetailPage />} />
              <Route path="/releases" element={<ReleasesPage />} />
              <Route path="/releases/:requirementId" element={<ReleaseDetailPage />} />
              <Route path="*" element={<Navigate to="/requirements" replace />} />
            </Routes>
          </main>
        </div>
      </div>
    </div>
  )
}
