---
id: analytics-frontend-sdk
title: Frontend Analytics SDK — lib/analytics.ts
role: cro_optimizer
status: draft
created_at: 2026-04-09
updated_at: 2026-04-09
author: cro_optimizer_agent
target_repo: Synapse-Network (services/user-front/)
---

# Frontend Analytics SDK

> 目标文件：`services/user-front/src/lib/analytics.ts`
>
> 所有前端事件统一通过此模块发射，不直接调用第三方 SDK。
> 前端只负责用户交互事件，计费/结算事件由 Gateway 服务端上报。

---

## 1. 核心模块：`lib/analytics.ts`

```typescript
/**
 * Synapse Analytics SDK — Frontend Event Emitter
 *
 * 职责：
 *   1. 统一封装所有前端埋点的 capture / identify / page 调用
 *   2. 将事件批量发送到 Gateway /api/v1/events 端点
 *   3. 提供 session_id、UTM、common properties 的自动注入
 *   4. 不直接耦合任何第三方 SDK（PostHog / GA4）
 *
 * 使用方式：
 *   import { analytics } from '@/lib/analytics';
 *   analytics.capture('cta_clicked', { cta_id: 'hero_signup', cta_text: 'Get Started' });
 */

import { v4 as uuidv4 } from 'uuid';

// ─── Types ────────────────────────────────────────────────────

export interface AnalyticsEvent {
  event_id: string;
  event_name: string;
  timestamp: string;
  distinct_id: string;
  source: 'frontend';
  properties: Record<string, unknown>;
}

export interface AnalyticsConfig {
  /** Gateway events endpoint. Defaults to /api/v1/events */
  endpoint: string;
  /** Current environment */
  env: 'local' | 'staging' | 'prod';
  /** Max events before auto-flush */
  batchSize: number;
  /** Max ms between flushes */
  flushIntervalMs: number;
  /** Enable console logging in dev */
  debug: boolean;
}

// ─── Defaults ─────────────────────────────────────────────────

const DEFAULT_CONFIG: AnalyticsConfig = {
  endpoint: process.env.NEXT_PUBLIC_ANALYTICS_ENDPOINT || '/api/v1/events',
  env: (process.env.NEXT_PUBLIC_ENV as AnalyticsConfig['env']) || 'local',
  batchSize: 10,
  flushIntervalMs: 5_000,
  debug: process.env.NODE_ENV === 'development',
};

// ─── Helpers ──────────────────────────────────────────────────

function getSessionId(): string {
  if (typeof window === 'undefined') return '';
  let sid = sessionStorage.getItem('synapse_session_id');
  if (!sid) {
    sid = uuidv4();
    sessionStorage.setItem('synapse_session_id', sid);
  }
  return sid;
}

function getAnonymousId(): string {
  if (typeof window === 'undefined') return '';
  let aid = localStorage.getItem('synapse_anonymous_id');
  if (!aid) {
    aid = uuidv4();
    localStorage.setItem('synapse_anonymous_id', aid);
  }
  return aid;
}

function parseUtmParams(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  const params = new URLSearchParams(window.location.search);
  const utm: Record<string, string> = {};
  for (const key of ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term']) {
    const val = params.get(key);
    if (val) {
      utm[key] = val;
      // Persist UTMs for the session so they survive SPA navigation
      sessionStorage.setItem(key, val);
    } else {
      const stored = sessionStorage.getItem(key);
      if (stored) utm[key] = stored;
    }
  }
  return utm;
}

/** SHA-256 hash a wallet address for privacy */
async function hashWallet(address: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(address.toLowerCase());
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

// ─── Analytics Class ──────────────────────────────────────────

class SynapseAnalytics {
  private config: AnalyticsConfig;
  private queue: AnalyticsEvent[] = [];
  private flushTimer: ReturnType<typeof setInterval> | null = null;
  private distinctId: string = '';
  private identifiedWalletHash: string = '';
  private role: 'anonymous' | 'consumer' | 'provider' = 'anonymous';
  private walletProvider: string = '';
  private chainId: number = 0;

  constructor(config: Partial<AnalyticsConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  // ── Lifecycle ─────────────────────────────────────────────

  /** Call once when the app mounts (e.g., in _app.tsx or layout.tsx) */
  init(): void {
    this.distinctId = getAnonymousId();
    // Capture UTM params on first load
    parseUtmParams();
    // Start background flush timer
    if (typeof window !== 'undefined' && !this.flushTimer) {
      this.flushTimer = setInterval(() => this.flush(), this.config.flushIntervalMs);
      // Flush on page unload
      window.addEventListener('beforeunload', () => this.flush());
      // Flush on visibility change (mobile tab switch)
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') this.flush();
      });
    }
  }

  /** Call after wallet connection to link anonymous → wallet identity */
  async identify(walletAddress: string, opts?: {
    role?: 'consumer' | 'provider';
    walletProvider?: string;
    chainId?: number;
  }): Promise<void> {
    this.identifiedWalletHash = await hashWallet(walletAddress);
    this.distinctId = this.identifiedWalletHash;
    if (opts?.role) this.role = opts.role;
    if (opts?.walletProvider) this.walletProvider = opts.walletProvider;
    if (opts?.chainId) this.chainId = opts.chainId;

    // Emit alias event to link anonymous_id → wallet_hash
    this.capture('$identify', {
      anonymous_id: getAnonymousId(),
      wallet_hash: this.identifiedWalletHash,
    });
  }

  /** Reset identity on disconnect */
  reset(): void {
    this.distinctId = getAnonymousId();
    this.identifiedWalletHash = '';
    this.role = 'anonymous';
    this.walletProvider = '';
    this.chainId = 0;
  }

  destroy(): void {
    if (this.flushTimer) {
      clearInterval(this.flushTimer);
      this.flushTimer = null;
    }
    this.flush();
  }

  // ── Event Capture ─────────────────────────────────────────

  /** Capture a named event with properties */
  capture(eventName: string, properties: Record<string, unknown> = {}): void {
    const event: AnalyticsEvent = {
      event_id: uuidv4(),
      event_name: eventName,
      timestamp: new Date().toISOString(),
      distinct_id: this.distinctId,
      source: 'frontend',
      properties: {
        ...this.commonProperties(),
        ...properties,
      },
    };

    this.queue.push(event);

    if (this.config.debug) {
      console.log('[analytics]', eventName, event.properties);
    }

    if (this.queue.length >= this.config.batchSize) {
      this.flush();
    }
  }

  /** Track SPA page navigation. Call on every route change. */
  page(pagePath?: string): void {
    this.capture('page_viewed', {
      page_path: pagePath || (typeof window !== 'undefined' ? window.location.pathname : ''),
      page_title: typeof document !== 'undefined' ? document.title : '',
      referrer: typeof document !== 'undefined' ? document.referrer : '',
    });
  }

  // ── Common Properties ─────────────────────────────────────

  private commonProperties(): Record<string, unknown> {
    const utm = parseUtmParams();
    return {
      role: this.role,
      surface: this.detectSurface(),
      env: this.config.env,
      chain_id: this.chainId || undefined,
      wallet_provider: this.walletProvider || undefined,
      session_id: getSessionId(),
      page_path: typeof window !== 'undefined' ? window.location.pathname : '',
      ...utm,
    };
  }

  private detectSurface(): string {
    if (typeof window === 'undefined') return 'unknown';
    const path = window.location.pathname;
    if (path.startsWith('/provider')) return 'provider_console';
    if (path.startsWith('/owner') || path.startsWith('/consumer')) return 'console';
    if (path.startsWith('/docs')) return 'docs';
    return 'landing';
  }

  // ── Flush / Send ──────────────────────────────────────────

  private async flush(): Promise<void> {
    if (this.queue.length === 0) return;

    const batch = this.queue.splice(0);

    try {
      // Use sendBeacon for unload scenarios, fetch for normal
      const payload = JSON.stringify({ events: batch });

      if (typeof navigator !== 'undefined' && navigator.sendBeacon) {
        const blob = new Blob([payload], { type: 'application/json' });
        const sent = navigator.sendBeacon(this.config.endpoint, blob);
        if (!sent) {
          // Fallback to fetch if sendBeacon fails
          await this.fetchSend(payload);
        }
      } else {
        await this.fetchSend(payload);
      }
    } catch (err) {
      if (this.config.debug) {
        console.error('[analytics] flush failed:', err);
      }
      // Re-enqueue failed events (cap at 100 to prevent memory leak)
      if (this.queue.length < 100) {
        this.queue.unshift(...batch);
      }
    }
  }

  private async fetchSend(payload: string): Promise<void> {
    await fetch(this.config.endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: payload,
      keepalive: true,
    });
  }
}

// ─── Singleton Export ─────────────────────────────────────────

export const analytics = new SynapseAnalytics();

// Re-export class for testing
export { SynapseAnalytics };
```

---

## 2. React Provider + Hook：`lib/analytics-provider.tsx`

```tsx
/**
 * AnalyticsProvider — 包裹在 app layout 中，自动处理：
 *   1. analytics.init() 初始化
 *   2. 路由变化时自动触发 page_viewed
 *   3. 钱包连接时自动 identify
 */
'use client';

import { useEffect, useRef } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { useAccount } from 'wagmi';
import { analytics } from './analytics';

export function AnalyticsProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { address, connector, chain } = useAccount();
  const prevPath = useRef<string>('');
  const identified = useRef(false);

  // Init on mount
  useEffect(() => {
    analytics.init();
    return () => analytics.destroy();
  }, []);

  // Track page views on route change
  useEffect(() => {
    const fullPath = searchParams?.toString()
      ? `${pathname}?${searchParams.toString()}`
      : pathname;

    if (fullPath !== prevPath.current) {
      analytics.page(pathname);
      prevPath.current = fullPath;
    }
  }, [pathname, searchParams]);

  // Identify on wallet connect
  useEffect(() => {
    if (address && !identified.current) {
      analytics.identify(address, {
        walletProvider: connector?.name || 'unknown',
        chainId: chain?.id,
      });
      identified.current = true;
    }
    if (!address && identified.current) {
      analytics.reset();
      identified.current = false;
    }
  }, [address, connector, chain]);

  return <>{children}</>;
}
```

### 在 Layout 中使用

```tsx
// app/layout.tsx
import { AnalyticsProvider } from '@/lib/analytics-provider';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html>
      <body>
        <WagmiProvider>
          <AnalyticsProvider>
            {children}
          </AnalyticsProvider>
        </WagmiProvider>
      </body>
    </html>
  );
}
```

---

## 3. 业务埋点示例

### 3.1 CTA 点击

```tsx
// components/HeroCTA.tsx
import { analytics } from '@/lib/analytics';

export function HeroCTA() {
  return (
    <button
      onClick={() => {
        analytics.capture('cta_clicked', {
          cta_id: 'hero_signup',
          cta_text: 'Start Building',
          cta_location: 'hero',
        });
      }}
    >
      Start Building
    </button>
  );
}
```

### 3.2 钱包连接

```tsx
// hooks/useWalletConnect.ts (在现有连接逻辑中埋点)
import { analytics } from '@/lib/analytics';

// 在钱包连接流程中:
function onConnectStart(walletProvider: string) {
  analytics.capture('wallet_connect_started', { wallet_provider: walletProvider });
}

function onConnectSuccess(address: string, walletProvider: string, chainId: number, isNew: boolean) {
  analytics.capture('wallet_connected', {
    wallet_provider: walletProvider,
    chain_id: chainId,
    is_new_user: isNew,
  });
  // identify 会自动在 AnalyticsProvider 中调用
}

function onConnectFailed(walletProvider: string, errorCode: string) {
  analytics.capture('wallet_connect_failed', {
    wallet_provider: walletProvider,
    error_code: errorCode,
  });
}
```

### 3.3 充值流程

```tsx
// 在充值组件中:
import { analytics } from '@/lib/analytics';

function onDepositStart(amountUsdc: number, tokenSymbol: string, chainId: number) {
  analytics.capture('deposit_started', {
    amount_usdc: amountUsdc,
    token_symbol: tokenSymbol,
    chain_id: chainId,
  });
}

function onPermitSigned(amountUsdc: number, tokenSymbol: string) {
  analytics.capture('deposit_permit_signed', {
    amount_usdc: amountUsdc,
    token_symbol: tokenSymbol,
  });
}
// Note: deposit_completed 由 gateway 服务端上报，前端不重复发
```

### 3.4 服务浏览

```tsx
// app/marketplace/page.tsx
import { analytics } from '@/lib/analytics';

function onSearch(query: string, resultsCount: number) {
  analytics.capture('service_search_executed', {
    query,
    results_count: resultsCount,
    surface: 'landing',
  });
}

function onServiceClick(serviceId: string, providerId: string, priceUsdc: number) {
  analytics.capture('service_detail_viewed', {
    service_id: serviceId,
    provider_id: providerId,
    price_usdc: priceUsdc,
  });
}
```

### 3.5 角色选择

```tsx
function onRoleSelected(role: 'consumer' | 'provider') {
  analytics.capture('role_selected', { role });
}
```

---

## 4. GA4 集成（仅流量归因）

```tsx
// app/layout.tsx — GA4 only for acquisition attribution
import Script from 'next/script';

const GA_MEASUREMENT_ID = process.env.NEXT_PUBLIC_GA4_ID;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html>
      <head>
        {GA_MEASUREMENT_ID && (
          <>
            <Script
              src={`https://www.googletagmanager.com/gtag/js?id=${GA_MEASUREMENT_ID}`}
              strategy="afterInteractive"
            />
            <Script id="ga4-init" strategy="afterInteractive">
              {`
                window.dataLayer = window.dataLayer || [];
                function gtag(){dataLayer.push(arguments);}
                gtag('js', new Date());
                gtag('config', '${GA_MEASUREMENT_ID}', {
                  send_page_view: true,
                  anonymize_ip: true,
                });
              `}
            </Script>
          </>
        )}
      </head>
      <body>
        <WagmiProvider>
          <AnalyticsProvider>
            {children}
          </AnalyticsProvider>
        </WagmiProvider>
      </body>
    </html>
  );
}
```

GA4 只做页面级流量归因（`page_view` + UTM），不做产品事件追踪。产品事件全走 Kafka pipeline。
