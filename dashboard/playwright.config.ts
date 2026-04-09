import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:19700',
    trace: 'on-first-retry',
  },
  webServer: [
    {
      command: 'cd .. && mkdir -p .playwright && rm -f .playwright/ops-e2e.sqlite && OPS_ENV=local OPS_PORT=19600 OPS_DATABASE_URL=sqlite:///$PWD/.playwright/ops-e2e.sqlite OPS_E2E_MODE=1 OPS_E2E_SYNC_DISPATCH=0 COPILOT_SDK_MONITOR_ENABLED=0 ../.venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port 19600 --log-level warning',
      url: 'http://127.0.0.1:19600/health',
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: 'OPS_DASHBOARD_API_PROXY_TARGET=http://127.0.0.1:19600 npm run dev -- --host 127.0.0.1 --port 19700',
      url: 'http://127.0.0.1:19700',
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})