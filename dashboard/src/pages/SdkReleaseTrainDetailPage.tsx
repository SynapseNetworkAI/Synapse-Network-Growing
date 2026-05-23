import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { SdkReleaseTrain, sdkPackagesApi } from '../sdkPackagesApi'
import { EmptyPane, LoadingPane, SectionFrame, StateBadge, useToast } from '../components/workbench'
import { SDK_PUBLIC_PACKAGE_LINKS, SDK_SOURCE_REPO_URL, SDK_STATUS_LABEL, formatSdkTime, openExternalUrl, sdkReleaseTone, syncSdkStatuses } from './sdkPackageUi'

export default function SdkReleaseTrainDetailPage() {
  const { version } = useParams<{ version: string }>()
  const navigate = useNavigate()
  const toast = useToast()
  const trainVersion = version || ''
  const [train, setTrain] = useState<SdkReleaseTrain | null>(null)
  const [loading, setLoading] = useState(true)
  const [busyAction, setBusyAction] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      setTrain(await sdkPackagesApi.getSdkReleaseTrain(trainVersion))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!trainVersion) return
    load().catch((error) => toast.error(error instanceof Error ? error.message : '加载 SDK release train 失败'))
  }, [trainVersion])

  const summary = useMemo(() => {
    if (!train) return []
    return Object.entries(train.status_counts).sort(([left], [right]) => left.localeCompare(right))
  }, [train])

  const dryRunPackage = async (id: number) => {
    setBusyAction(`dry-run-${id}`)
    try {
      await sdkPackagesApi.dryRunSdkPackageRelease(id, { actor: 'operator', note: `Dry run from train ${trainVersion}` })
      toast.success('Dry run 已触发')
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Dry run 失败')
    } finally {
      setBusyAction(null)
    }
  }

  const dryRunAllPlanned = async () => {
    if (!train) return
    const planned = train.packages.filter((item) => item.status === 'planned')
    if (!planned.length) {
      toast.info('没有 planned package 需要 dry-run')
      return
    }
    setBusyAction('dry-run-all')
    try {
      for (const item of planned) {
        await sdkPackagesApi.dryRunSdkPackageRelease(item.id, { actor: 'operator', note: `Batch dry run from train ${trainVersion}` })
      }
      toast.success(`已触发 ${planned.length} 个 package dry-run`)
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '批量 dry-run 失败')
    } finally {
      setBusyAction(null)
    }
  }

  const syncAll = async () => {
    await syncSdkStatuses({ load, setBusyAction, toast, busyKey: 'sync-all' })
  }

  if (loading || !train) {
    return <LoadingPane>正在加载 SDK release train…</LoadingPane>
  }

  return (
    <div className="space-y-[var(--ops-section-gap)]">
      <SectionFrame
        eyebrow="SDK Release Train"
        title={`Release Train ${train.release_train_version}`}
        description="这是 SDK 发布矩阵。可以批量 dry-run / sync，但不提供一键 publish all，避免误发布到真实 registry。"
        actions={
          <>
            <button type="button" className="rounded-2xl border border-[color:var(--ops-state-ready-border)] px-4 py-2 text-sm text-[color:var(--ops-state-ready-text)] disabled:opacity-60" disabled={Boolean(busyAction)} onClick={dryRunAllPlanned}>
              {busyAction === 'dry-run-all' ? 'Dry Run All 中…' : 'Dry Run All Planned'}
            </button>
            <button type="button" className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm disabled:opacity-60" disabled={Boolean(busyAction)} onClick={syncAll}>
              {busyAction === 'sync-all' ? '同步中…' : 'Sync All'}
            </button>
            <button type="button" className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate('/releases')}>
              返回 Releases
            </button>
          </>
        }
      >
        <div className="flex flex-wrap gap-2">
          <StateBadge tone="muted">{train.channel}</StateBadge>
          <StateBadge tone="muted">{train.package_count} packages</StateBadge>
          {summary.map(([status, count]) => (
            <StateBadge key={status} tone={sdkReleaseTone(status)}>{SDK_STATUS_LABEL[status] || status}: {count}</StateBadge>
          ))}
        </div>
        <div className="mt-4 grid gap-3 text-sm text-[color:var(--ops-text-muted)] md:grid-cols-2">
          <div>created：{formatSdkTime(train.created_at)}</div>
          <div>updated：{formatSdkTime(train.updated_at)}</div>
        </div>
      </SectionFrame>

      <SectionFrame eyebrow="Public SDK Links" title="1.0.0 公共仓库入口">
        <div className="grid gap-3 lg:grid-cols-2">
          {SDK_PUBLIC_PACKAGE_LINKS.map((link) => (
            <article key={link.language} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="font-semibold text-[color:var(--ops-text-title)]">{link.language} · {link.registry}</div>
                  <div className="mt-1 break-all font-mono text-xs text-[color:var(--ops-text-caption)]">{link.packageName}</div>
                </div>
                <StateBadge tone="delivered">published</StateBadge>
              </div>
              <div className="mt-3 rounded-xl border border-[color:var(--ops-stroke-soft)] bg-black/20 px-3 py-2 font-mono text-xs text-[color:var(--ops-text-muted)]">
                {link.installCommand}
              </div>
              <button type="button" className="mt-3 rounded-xl border border-[color:var(--ops-state-running-border)] px-3 py-2 text-sm text-[color:var(--ops-state-running-text)]" onClick={() => openExternalUrl(link.url)}>
                打开 {link.registry}
              </button>
            </article>
          ))}
        </div>
        <button type="button" className="mt-4 rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => openExternalUrl(SDK_SOURCE_REPO_URL)}>
          查看 GitHub SDK repo
        </button>
      </SectionFrame>

      <SectionFrame eyebrow="Release Matrix" title="Package 发布矩阵">
        {train.packages.length ? (
          <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
            {train.packages.map((item) => (
              <article key={item.id} className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5">
                <div className="flex items-start justify-between gap-3">
                  <button type="button" className="text-left" onClick={() => navigate(`/releases/sdk-packages/${item.id}`)}>
                    <div className="font-semibold text-[color:var(--ops-text-title)]">{item.sdk_language}</div>
                    <div className="mt-1 text-sm text-[color:var(--ops-text-muted)]">{item.package_name}</div>
                  </button>
                  <StateBadge tone={sdkReleaseTone(item.status)}>{SDK_STATUS_LABEL[item.status] || item.status}</StateBadge>
                </div>
                <div className="mt-4 grid gap-2 text-xs text-[color:var(--ops-text-muted)]">
                  <div>Registry: <span className="font-mono">{item.registry}</span></div>
                  <div>Channel: <span className="font-mono">{item.channel}</span></div>
                  <div>Version: <span className="font-mono">{item.package_version}</span></div>
                  <div>Git tag: <span className="font-mono">{item.git_tag || '-'}</span></div>
                </div>
                {item.failure_summary ? <div className="mt-3 line-clamp-2 text-xs text-[color:var(--ops-state-blocked-text)]">{item.failure_summary}</div> : null}
                <div className="mt-4 flex flex-wrap gap-2">
                  <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigate(`/releases/sdk-packages/${item.id}`)}>
                    发布详情
                  </button>
                  {item.status === 'planned' ? (
                    <button type="button" className="rounded-xl border border-[color:var(--ops-state-ready-border)] px-3 py-2 text-sm text-[color:var(--ops-state-ready-text)] disabled:opacity-60" disabled={Boolean(busyAction)} onClick={() => dryRunPackage(item.id)}>
                      {busyAction === `dry-run-${item.id}` ? '验证中…' : 'Dry Run'}
                    </button>
                  ) : null}
                  {item.workflow_run_url ? (
                    <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => openExternalUrl(item.workflow_run_url)}>
                      Workflow
                    </button>
                  ) : null}
                  {item.package_url ? (
                    <button type="button" className="rounded-xl border border-[color:var(--ops-state-running-border)] px-3 py-2 text-sm text-[color:var(--ops-state-running-text)]" onClick={() => openExternalUrl(item.package_url)}>
                      Package
                    </button>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyPane>这个 train 暂无 package records。</EmptyPane>
        )}
      </SectionFrame>
    </div>
  )
}
