import { useEffect, useState } from 'react'
import {
  api,
  type SocialContentAsset,
  type SocialContentAssetDetail,
  type SocialDistributionAccount,
} from '../api'
import { EmptyPane, OverlayModal, SectionFrame, useToast } from './workbench'
import { AssetSummary } from './SocialDistributionBoard'
import { AssetDetail } from './SocialDistributionDetails'
import { AssetForm } from './SocialDistributionWidgets'

export function DistributionAssetsPanel({ formatDateTime }: { formatDateTime: (value: string | null | undefined) => string }) {
  const toast = useToast()
  const [assets, setAssets] = useState<SocialContentAsset[]>([])
  const [accounts, setAccounts] = useState<SocialDistributionAccount[]>([])
  const [detail, setDetail] = useState<SocialContentAssetDetail | null>(null)
  const [selectedAccountIds, setSelectedAccountIds] = useState<number[]>([])
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ title: '', summary: '', body: '', canonical_url: '', asset_type: 'article' })
  const [busyAssetId, setBusyAssetId] = useState<number | null>(null)
  const [plannerBusy, setPlannerBusy] = useState(false)

  async function loadAssets() {
    try {
      const [assetRows, accountRows] = await Promise.all([api.getSocialContentAssets(), api.getDistributionAccounts()])
      setAssets(assetRows)
      setAccounts(accountRows)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载内容资产失败')
    }
  }

  useEffect(() => {
    void loadAssets()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function createAsset() {
    try {
      const created = await api.createSocialContentAsset({ ...form, source_type: 'manual', created_by: 'operator' })
      setShowCreate(false)
      setForm({ title: '', summary: '', body: '', canonical_url: '', asset_type: 'article' })
      setDetail(created)
      await loadAssets()
      toast.success('内容资产已创建')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '创建内容资产失败')
    }
  }

  async function openAsset(id: number) {
    try {
      const row = await api.getSocialContentAsset(id)
      setDetail(row)
      setSelectedAccountIds(row.tasks.map((task) => task.account_id))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载资产详情失败')
    }
  }

  async function runAssetPlanner() {
    try {
      setPlannerBusy(true)
      const result = await api.runSocialAssetPlanner()
      if (result.asset) {
        setDetail(result.asset)
        setSelectedAccountIds(result.asset.tasks.map((task) => task.account_id))
        toast.success(`Asset Planner 已生成：${result.asset.title}`)
      } else {
        toast.success(result.already_satisfied ? '今日 Asset 库存已满足' : `未生成 Asset：${result.reason ?? 'no qualified signal'}`)
      }
      await loadAssets()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '运行 Asset Planner 失败')
    } finally {
      setPlannerBusy(false)
    }
  }

  async function expandCanonicalArticle(asset: SocialContentAssetDetail | SocialContentAsset) {
    try {
      setBusyAssetId(asset.id)
      const updated = await api.expandSocialDistributionCanonicalArticle(asset.id, { actor: 'operator' })
      setDetail(updated)
      await loadAssets()
      toast.success('母稿已扩写，等待人工审核')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '扩写母稿失败')
    } finally {
      setBusyAssetId(null)
    }
  }

  async function approveCanonicalArticle(asset: SocialContentAssetDetail) {
    try {
      setBusyAssetId(asset.id)
      const canonicalArticle = latestAssetDocument(asset, 'canonical_article')
      const updated = await api.approveSocialDistributionCanonicalArticle(asset.id, {
        actor: 'operator',
        document_id: canonicalArticle?.id ?? null,
      })
      setDetail(updated)
      await loadAssets()
      toast.success('母稿已审核通过，可以生成平台任务')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '审核母稿失败')
    } finally {
      setBusyAssetId(null)
    }
  }

  async function approveAndGenerate(asset: SocialContentAssetDetail | SocialContentAsset) {
    try {
      setBusyAssetId(asset.id)
      const result = await api.approveAndGenerateSocialDistributionTasks(asset.id, {
        account_ids: detail?.id === asset.id ? selectedAccountIds : [],
        action: 'post',
        actor: 'operator',
      })
      setDetail(result.asset)
      setSelectedAccountIds(result.asset.tasks.map((task) => task.account_id))
      await loadAssets()
      toast.success(`批准并生成完成：${result.generated_task_ids.length} 成功，${result.failed_task_ids.length} 失败`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '批准并生成渠道任务失败')
    } finally {
      setBusyAssetId(null)
    }
  }

  return (
    <SectionFrame
      eyebrow="Content Assets"
      title="Assets"
      description="一份源内容可以派生出多个平台任务；资产是新的 Social Distribution Source of Truth。"
      actions={
        <div className="flex flex-wrap gap-2">
          <button type="button" disabled={plannerBusy} className="rounded-xl border border-cyan-300/40 px-4 py-2 text-sm font-semibold text-cyan-100 disabled:opacity-50" onClick={() => void runAssetPlanner()}>
            {plannerBusy ? 'Asset Planner 运行中…' : '运行 Asset Planner'}
          </button>
          <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white" onClick={() => setShowCreate(true)}>创建内容资产</button>
        </div>
      }
    >
      {assets.length === 0 ? <EmptyPane>暂无内容资产。</EmptyPane> : null}
      <div className="grid gap-3 lg:grid-cols-2">
        {assets.map((asset) => {
          const busy = busyAssetId === asset.id
          return (
            <article key={asset.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-4">
              <button type="button" className="w-full text-left" onClick={() => void openAsset(asset.id)}>
                <AssetSummary asset={asset} taskCount={asset.task_count} />
                <div className="mt-3 text-xs text-[color:var(--ops-text-caption)]">updated {formatDateTime(asset.updated_at)}</div>
              </button>
              <div className="mt-4 flex flex-wrap gap-2">
                <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => void openAsset(asset.id)}>详情</button>
                <button type="button" disabled={busy} className="rounded-xl border border-cyan-300/40 px-3 py-2 text-sm font-semibold text-cyan-100 disabled:opacity-50" onClick={() => void expandCanonicalArticle(asset)}>
                  {busy ? '扩写中…' : '扩写母稿'}
                </button>
              </div>
            </article>
          )
        })}
      </div>
      <OverlayModal open={showCreate} eyebrow="Content Asset" title="创建内容资产" description="输入源文章、demo 或官方公告摘要；系统随后为各平台串行生成任务。" actions={<button type="button" className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white" onClick={() => void createAsset()}>创建</button>} onClose={() => setShowCreate(false)}>
        <AssetForm form={form} onChange={setForm} />
      </OverlayModal>
      <OverlayModal
        open={Boolean(detail)}
        eyebrow="Content Asset"
        title={detail?.title ?? '内容资产'}
        description="先扩写并审核 canonical_article 母稿，再按平台信息密度适配；某个平台失败不会回滚其它平台。"
        actions={
          <AssetModalActions
            asset={detail}
            busy={Boolean(detail && busyAssetId === detail.id)}
            onExpand={() => detail ? void expandCanonicalArticle(detail) : undefined}
            onApproveCanonical={() => detail ? void approveCanonicalArticle(detail) : undefined}
            onApproveGenerate={() => detail ? void approveAndGenerate(detail) : undefined}
          />
        }
        onClose={() => setDetail(null)}
      >
        {detail ? <AssetDetail asset={detail} accounts={accounts} selectedAccountIds={selectedAccountIds} formatDateTime={formatDateTime} onToggle={(id) => setSelectedAccountIds((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id])} /> : null}
      </OverlayModal>
    </SectionFrame>
  )
}

function latestAssetDocument(asset: SocialContentAssetDetail | null, kind: string) {
  return (asset?.documents ?? [])
    .filter((doc) => doc.document_kind === kind)
    .sort((left, right) => {
      if (right.version !== left.version) return right.version - left.version
      return String(right.updated_at ?? '').localeCompare(String(left.updated_at ?? ''))
    })[0]
}

function AssetModalActions({
  asset,
  busy,
  onExpand,
  onApproveCanonical,
  onApproveGenerate,
}: {
  asset: SocialContentAssetDetail | null
  busy: boolean
  onExpand: () => void
  onApproveCanonical: () => void
  onApproveGenerate: () => void
}) {
  const canonicalArticle = latestAssetDocument(asset, 'canonical_article')
  if (!asset || !canonicalArticle) {
    return (
      <button type="button" disabled={!asset || busy} className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" onClick={onExpand}>
        {busy ? '扩写中…' : '扩写母稿'}
      </button>
    )
  }
  if (canonicalArticle.status !== 'approved') {
    return (
      <button type="button" disabled={busy} className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" onClick={onApproveCanonical}>
        {busy ? '审核中…' : '审核通过母稿'}
      </button>
    )
  }
  return (
    <button type="button" disabled={busy} className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" onClick={onApproveGenerate}>
      {busy ? '生成中…' : '批准并生成平台任务'}
    </button>
  )
}
