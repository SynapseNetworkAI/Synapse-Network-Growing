Done. Here's a summary of what was implemented:

## Frontend Tracking Implementation ✅

**3 files changed:**

### 1. `src/app/layout.tsx`
- Imported and wrapped the app with `AnalyticsProvider`
- Placed inside `<Providers>` so it has access to wagmi's `useAccount`
- Automatically handles: `page_viewed` on every route change, `$identify` on wallet connect, `reset()` on disconnect

### 2. `src/app/page.tsx`
Added tracking for 4 key events:
- `cta_clicked` — hero "Launch Console" button (`cta_id: hero_launch_console`)  
- `cta_clicked` — hero "Open Developer Resources" button
- `cta_clicked` — bottom CTA section (consumer + provider buttons)
- `role_selected` — whenever user picks consumer or provider role

### 3. `src/hooks/useVaultDeposit.ts`
Added 2 deposit funnel events:
- `deposit_started` — fires when user submits amount and permit is requested (`amount_usdc`, `token_symbol`, `chain_id`)
- `deposit_permit_signed` — fires after EIP-2612 permit signature succeeds, before tx broadcast

**Test results:** All 8 analytics unit tests pass ✅. The 1 remaining failure is a pre-existing wagmi mock issue in an unrelated test file (was 15 failures before my changes).