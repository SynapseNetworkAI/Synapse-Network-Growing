import { useEffect, useState } from 'react'
import { api, RecurringWorkflowHealth } from '../api'
import { ActionButton, AgentReasoningCard, CockpitPanel, MetricTile } from '../components/controlPlane'

function readNumber(value: unknown) {
  return typeof value === 'number' ? value : 0
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

export default function NotificationsPage() {
  const [health, setHealth] = useState<RecurringWorkflowHealth | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    setError(null)
    api.getRecurringWorkflowHealth()
      .then(setHealth)
      .catch((err) => setError(err.message || String(err)))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const dispatcher = record(health?.notification_dispatcher)
  const registry = record(health?.recurring_registry)

  return (
    <div className="space-y-6">
      <CockpitPanel
        eyebrow="System Ops"
        title="通知与告警队列"
        description="Lark 不是完整状态源，只负责把需要人知道的事件推到正确群。队列、抑制、cooldown 和 dead letter 必须可观测。"
        actions={<ActionButton onClick={load}>刷新</ActionButton>}
      >
        <div className="grid gap-4 md:grid-cols-4">
          <MetricTile label="Dispatcher" value={String(dispatcher.enabled ?? dispatcher.running ?? 'unknown')} detail="后台 notification dispatcher 状态" tone="info" />
          <MetricTile label="Queued" value={readNumber(dispatcher.queued_count)} detail="等待发送或重试的事件" tone={readNumber(dispatcher.queued_count) ? 'warning' : 'muted'} />
          <MetricTile label="Dead Letter" value={readNumber(dispatcher.dead_letter_count)} detail="超过重试次数的投递" tone={readNumber(dispatcher.dead_letter_count) ? 'danger' : 'muted'} />
          <MetricTile label="Open Fingerprints" value={readNumber(dispatcher.open_fingerprint_count)} detail="仍处于 open 的告警指纹" tone="info" />
        </div>
      </CockpitPanel>

      {error ? <AgentReasoningCard title="Notification health failed to load" tone="danger" summary={error} /> : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <AgentReasoningCard
          title="Notification policy"
          tone="info"
          summary="业务代码只 enqueue notification event。dispatcher 统一做 dedupe、限流、抑制、rollup、发送和重试。"
          metadata={loading ? 'Loading...' : JSON.stringify(dispatcher, null, 2)}
        />
        <AgentReasoningCard
          title="Recurring registry"
          tone="warning"
          summary="定时任务和告警 dispatcher 都必须进入 System Ops 管理面，不能藏在线程或日志里。"
          metadata={JSON.stringify(registry, null, 2)}
        />
      </div>
    </div>
  )
}
