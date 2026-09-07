import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60000,
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: { baseURL: "http://localhost:3100", trace: "on-first-retry" },
  projects: [
    { name: "webkit", use: { ...devices["iPhone 8"] } },
    { name: "chromium", use: { ...devices["Pixel 5"] } },
  ],
  webServer: {
    command: "pnpm run build && cp public/fake-host.html dist/ && pnpm run preview",
    url: "http://localhost:3100/fake-host.html",
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
});
