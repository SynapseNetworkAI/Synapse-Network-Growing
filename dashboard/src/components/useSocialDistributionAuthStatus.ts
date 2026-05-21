import { useState } from 'react'
import type { SocialDistributionAccountAuthStatus } from '../apiSocialDistribution'
import { api } from '../api'
import { useToast } from './workbench'

export function useSocialDistributionAuthStatus() {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [authStatuses, setAuthStatuses] = useState<Record<number, SocialDistributionAccountAuthStatus>>({})

  async function checkAccountAuthStatuses() {
    try {
      setBusy(true)
      const result = await api.getDistributionAccountAuthStatuses()
      setAuthStatuses(Object.fromEntries(result.items.map((item) => [item.account_id, item])))
      toast.success('登录/API 状态已检查')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '检查登录状态失败')
    } finally {
      setBusy(false)
    }
  }

  return { authStatuses, authStatusBusy: busy, checkAccountAuthStatuses }
}
