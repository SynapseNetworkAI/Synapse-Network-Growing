import { useEffect, useState } from 'react'
import { api, type SocialDistributionAccount } from '../api'
import type { SocialDistributionAccountAuthStatus } from '../apiSocialDistribution'
import { OverlayModal, SectionFrame, useToast } from './workbench'
import { useSocialDistributionAuthStatus } from './useSocialDistributionAuthStatus'
import {
  AccountForm,
  Pager,
  StateBadge,
  TaskLikeTable,
  pageSlice,
  statusTone,
} from './SocialDistributionWidgets'

export function DistributionSettingsPanel({ formatDateTime }: { formatDateTime: (value: string | null | undefined) => string }) {
  const toast = useToast()
  const [accounts, setAccounts] = useState<SocialDistributionAccount[]>([])
  const { authStatuses, authStatusBusy, checkAccountAuthStatuses } = useSocialDistributionAuthStatus()
  const [editing, setEditing] = useState<SocialDistributionAccount | null>(null)
  const [form, setForm] = useState({
    profile_url: '',
    status: 'planned',
    email_hint: '',
    two_factor_status: 'unknown',
    publish_mode: 'manual_only',
    api_capability: 'none',
    credential_ref: '',
    notes: '',
  })
  const [page, setPage] = useState(1)

  async function loadAccounts() {
    try {
      setAccounts(await api.getDistributionAccounts())
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载渠道失败')
    }
  }

  useEffect(() => {
    void loadAccounts()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function saveAccount() {
    if (!editing) return
    try {
      await api.updateDistributionAccount(editing.id, {
        ...form,
        credential_ref: form.credential_ref.trim() ? form.credential_ref : undefined,
      })
      setEditing(null)
      await loadAccounts()
      toast.success('渠道设置已保存')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '保存失败')
    }
  }

  const paged = pageSlice(accounts, page)
  return (
    <SectionFrame
      eyebrow="Settings"
      title="Settings"
      description="管理分发渠道账号、Profile、2FA 状态和人工发布规则。登录状态是实时检查结果，不作为永久 DB 事实源。"
      actions={<button type="button" disabled={authStatusBusy} className="rounded-xl border border-cyan-300/40 px-4 py-2 text-sm font-semibold text-cyan-100 disabled:opacity-50" onClick={() => void checkAccountAuthStatuses()}>{authStatusBusy ? '检查中…' : '检查登录状态'}</button>}
    >
      <TaskLikeTable
        headers={['平台 / 渠道', '账号状态', '发布路径', '更新', '操作']}
        rows={paged.map((account) => accountRow(account, authStatuses[account.id], formatDateTime, setEditing, setForm))}
      />
      <Pager page={page} total={accounts.length} onPageChange={setPage} />
      <OverlayModal open={Boolean(editing)} eyebrow="Distribution Account" title={editing ? `编辑 ${editing.display_name}` : '编辑渠道'} actions={<button type="button" className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white" onClick={() => void saveAccount()}>保存</button>} onClose={() => setEditing(null)}>
        <AccountForm form={form} onChange={setForm} />
      </OverlayModal>
    </SectionFrame>
  )
}

function accountRow(
  account: SocialDistributionAccount,
  auth: SocialDistributionAccountAuthStatus | undefined,
  formatDateTime: (value: string | null | undefined) => string,
  setEditing: (account: SocialDistributionAccount) => void,
  setForm: (value: {
    profile_url: string
    status: string
    email_hint: string
    two_factor_status: string
    publish_mode: string
    api_capability: string
    credential_ref: string
    notes: string
  }) => void,
) {
  const loginUrl = auth?.login_url || account.signup_url || account.profile_url
  return [
    <div key="name"><b>{account.display_name}</b><div className="font-mono text-xs text-[color:var(--ops-text-caption)]">{account.platform} · {account.channel_key}</div></div>,
    <div key="status" className="space-y-2">
      <StateBadge tone={statusTone(account.status)}>{account.status}</StateBadge>
      <div className="text-xs text-[color:var(--ops-text-muted)]">2FA {account.two_factor_status}{account.credential_ref_configured ? ' · secret ref set' : ''}</div>
    </div>,
    <div key="gov" className="max-w-md text-xs text-[color:var(--ops-text-muted)]">
      {auth ? (
        <>
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <StateBadge tone={publishPathTone(auth.publish_path)}>{publishPathLabel(auth.publish_path)}</StateBadge>
            {auth.api_supported ? <span className="font-mono text-[color:var(--ops-text-caption)]">API supported</span> : null}
          </div>
          <div>API: {auth.api_status} · Browser: {auth.browser_status}</div>
          {auth.blockers.length ? <div className="mt-1 text-amber-100">Blockers: {auth.blockers.join(', ')}</div> : null}
          <div className="mt-1">{auth.next_action}</div>
        </>
      ) : (
        <div>{account.publish_mode} · {account.api_capability} · 点击“检查登录状态”获取实时发布路径。</div>
      )}
    </div>,
    <span key="time" className="text-xs text-[color:var(--ops-text-muted)]">{formatDateTime(account.updated_at)}</span>,
    <div key="actions" className="flex flex-wrap gap-2">
      {loginUrl ? <a className="rounded-xl border border-emerald-300/40 px-3 py-2 text-sm text-emerald-100" href={loginUrl} target="_blank" rel="noreferrer">登录 / 打开平台</a> : null}
      <button type="button" className="rounded-xl border border-cyan-300/40 px-3 py-2 text-sm text-cyan-100" onClick={() => { window.location.href = `/publishing?tab=tasks&platform=${encodeURIComponent(account.platform)}&channel_key=${encodeURIComponent(account.channel_key)}` }}>历史</button>
      <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => startEditing(account, setEditing, setForm)}>编辑</button>
    </div>,
  ]
}

function startEditing(
  account: SocialDistributionAccount,
  setEditing: (account: SocialDistributionAccount) => void,
  setForm: Parameters<typeof accountRow>[4],
) {
  setEditing(account)
  setForm({
    profile_url: account.profile_url ?? '',
    status: account.status,
    email_hint: account.email_hint ?? '',
    two_factor_status: account.two_factor_status,
    publish_mode: account.publish_mode,
    api_capability: account.api_capability,
    credential_ref: '',
    notes: account.notes ?? '',
  })
}

function publishPathLabel(value: string): string {
  if (value === 'official_api') return '官方 API'
  if (value === 'browser_assisted') return '浏览器辅助'
  if (value === 'blocked') return '已阻断'
  return '人工发布'
}

function publishPathTone(value: string): 'ready' | 'running' | 'blocked' | 'validating' | 'delivered' | 'muted' {
  if (value === 'official_api' || value === 'browser_assisted') return 'ready'
  if (value === 'blocked') return 'blocked'
  return 'muted'
}
