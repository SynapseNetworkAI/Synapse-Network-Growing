import { Routes, Route, NavLink, useLocation } from 'react-router-dom'
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

const requirementSubNavItems = [
  { to: '/requirements?bucket=running', label: '运行中' },
  { to: '/requirements?bucket=pending', label: '待审批' },
  { to: '/requirements?bucket=closed', label: '已结束' },
  { to: '/requirements?bucket=deleted', label: '废弃/删除' },
]

const routeBriefs = [
  {
    match: (pathname: string) => pathname === '/',
    eyebrow: 'Company Operating Review',
    title: '公司操作系统工作台',
    description: '把组织、portfolio scheduler、optimization signals 和 next-cycle bundle 放在同一块决策界面里。',
    chips: ['live backend', 'company review', 'operator package'],
  },
  {
    match: (pathname: string) => pathname === '/requirements',
    eyebrow: 'Execution Queue',
    title: '需求池与交付节奏',
    description: '围绕优先级、验证闭环和跨项目调度，管理每一条可执行 requirement 的状态和顺序。',
    chips: ['queue', 'validation', 'delivery gate'],
  },
  {
    match: (pathname: string) => pathname.startsWith('/requirements/'),
    eyebrow: 'Requirement Detail',
    title: '单条 Requirement 指挥台',
    description: '查看 workflow、validation contract、delivery state 和 bugfix 证据，逐项推进到完成。',
    chips: ['workflow', 'artifacts', 'release-ready'],
  },
  {
    match: (pathname: string) => pathname === '/optimization-signals',
    eyebrow: 'Optimization Signal Ingestion',
    title: '优化信号收束面',
    description: '汇总 bug report、manual override 和 delivery blocker，把问题沉淀成可转 requirement 的优化机会。',
    chips: ['signals', 'auto intake', 'templates'],
  },
  {
    match: (pathname: string) => pathname === '/project-policies',
    eyebrow: 'Policy Registry',
    title: '项目策略与接入治理',
    description: '定义每个项目的边界、调度权重、自治模式和预算，决定 agent 能安全走到哪一步。',
    chips: ['policy', 'autonomy', 'budget'],
  },
  {
    match: (pathname: string) => pathname === '/tasks',
    eyebrow: 'Task Runtime',
    title: '任务执行面板',
    description: '观察 agent runtime、批量重试、输出文件和 requirement 关联，让执行细节保持可追踪。',
    chips: ['runtime', 'taskboard', 'evidence'],
  },
  {
    match: (pathname: string) => pathname.startsWith('/tasks/'),
    eyebrow: 'Task Detail',
    title: '任务实例细节',
    description: '从单次运行视角检查日志、文件变更和 requirement 回链，定位具体任务的执行结果。',
    chips: ['logs', 'file changes', 'history'],
  },
  {
    match: (pathname: string) => pathname === '/approvals',
    eyebrow: 'Operator Decisions',
    title: '审批中心',
    description: '处理需要人工判断的动作，把高风险变更、批量审批和 operator comment 集中到一个地方。',
    chips: ['approval', 'operator', 'risk gate'],
  },
]

function getRouteBrief(pathname: string) {
  return routeBriefs.find((item) => item.match(pathname)) ?? routeBriefs[0]
}

export default function App() {
  const location = useLocation()
  const brief = getRouteBrief(location.pathname)
  const requirementsNavActive = location.pathname.startsWith('/requirements')

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(64,97,255,0.18),_transparent_28%),radial-gradient(circle_at_top_right,_rgba(32,201,151,0.14),_transparent_24%),linear-gradient(180deg,_#f6f8fc_0%,_#eef2f7_100%)] text-slate-900">
      <div className="mx-auto flex min-h-screen max-w-[1560px] gap-4 px-3 py-3 md:px-5 md:py-5">
        <aside className="hidden w-[270px] shrink-0 flex-col rounded-[30px] border border-white/70 bg-[rgba(10,18,36,0.92)] px-5 py-5 text-slate-100 shadow-[0_24px_80px_rgba(15,23,42,0.24)] lg:flex">
          <div className="rounded-[24px] border border-white/10 bg-white/5 p-4">
            <div className="text-[11px] uppercase tracking-[0.24em] text-sky-200/80">Synapse Network Growing</div>
            <div className="mt-3 text-2xl font-semibold tracking-tight">Synapse Ops</div>
            <p className="mt-2 text-sm leading-6 text-slate-300">
              AI company operating system for routing work, supervising delivery, and compounding operational knowledge.
            </p>
          </div>

          <div className="mt-5 text-[11px] uppercase tracking-[0.22em] text-slate-400">Workspace</div>
          <nav className="mt-3 space-y-1.5">
            {navItems.map((n) => (
              <div key={n.to}>
                <NavLink
                  to={n.to}
                  end={n.to !== '/requirements'}
                  className={({ isActive }) =>
                    `block rounded-2xl px-4 py-3 text-sm transition ${
                      isActive || (n.to === '/requirements' && requirementsNavActive)
                        ? 'bg-[linear-gradient(135deg,rgba(91,124,250,0.96),rgba(48,180,255,0.92))] text-white shadow-[0_16px_32px_rgba(59,130,246,0.25)]'
                        : 'text-slate-300 hover:bg-white/6 hover:text-white'
                    }`
                  }
                >
                  {n.label}
                </NavLink>
                {n.to === '/requirements' && requirementsNavActive && (
                  <div className="mt-1 ml-3 space-y-1 border-l border-white/10 pl-3">
                    {requirementSubNavItems.map((sub) => {
                      const subActive = `${location.pathname}${location.search}` === sub.to
                      return (
                        <NavLink
                          key={sub.to}
                          to={sub.to}
                          className={`block rounded-xl px-3 py-2 text-xs transition ${
                            subActive
                              ? 'bg-white/10 text-white'
                              : 'text-slate-400 hover:bg-white/6 hover:text-white'
                          }`}
                        >
                          {sub.label}
                        </NavLink>
                      )
                    })}
                  </div>
                )}
              </div>
            ))}
          </nav>

          <div className="mt-auto rounded-[24px] border border-white/10 bg-white/5 p-4">
            <div className="text-[11px] uppercase tracking-[0.22em] text-slate-400">Mode</div>
            <div className="mt-2 text-sm font-medium text-white">Live backend connected</div>
            <p className="mt-2 text-xs leading-5 text-slate-300">
              当前界面优先展示调度、验证和 operator decision，而不是传统的卡片仪表盘。
            </p>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <div className="overflow-x-auto rounded-[26px] border border-white/80 bg-white/70 px-3 py-2 shadow-[0_12px_44px_rgba(148,163,184,0.14)] backdrop-blur md:px-5 lg:hidden">
            <div className="flex min-w-max items-center gap-2">
              {navItems.map((n) => (
                <NavLink
                  key={n.to}
                  to={n.to}
                  end={n.to !== '/requirements'}
                  className={({ isActive }) =>
                    `rounded-xl px-3 py-2 text-sm transition ${
                      isActive || (n.to === '/requirements' && requirementsNavActive)
                        ? 'bg-slate-900 text-white'
                        : 'text-slate-600 hover:bg-slate-100'
                    }`
                  }
                >
                  {n.label}
                </NavLink>
              ))}
            </div>
            {requirementsNavActive && (
              <div className="mt-2 flex min-w-max items-center gap-2 border-t border-slate-200 pt-2">
                {requirementSubNavItems.map((sub) => {
                  const subActive = `${location.pathname}${location.search}` === sub.to
                  return (
                    <NavLink
                      key={sub.to}
                      to={sub.to}
                      className={`rounded-xl px-3 py-1.5 text-xs transition ${
                        subActive ? 'bg-slate-900 text-white' : 'text-slate-500 hover:bg-slate-100'
                      }`}
                    >
                      {sub.label}
                    </NavLink>
                  )
                })}
              </div>
            )}
          </div>

          <header className="rounded-[30px] border border-white/80 bg-white/72 px-5 py-5 shadow-[0_18px_60px_rgba(148,163,184,0.16)] backdrop-blur md:px-7 md:py-6">
            <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
              <div className="max-w-3xl">
                <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">{brief.eyebrow}</div>
                <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 md:text-[2.35rem]">
                  {brief.title}
                </h1>
                <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-600 md:text-[15px]">
                  {brief.description}
                </p>
              </div>
              <div className="grid gap-3 sm:grid-cols-3 xl:w-[440px]">
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
      </div>
    </div>
  )
}
