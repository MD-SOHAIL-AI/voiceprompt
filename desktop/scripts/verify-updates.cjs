/* Explicit sample UI: native trust and engine handoff have separate checks. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { chromium, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;
const root = path.resolve(__dirname, "../..");
const output = path.join(root, "build", "updates-ui");
fs.mkdirSync(output, { recursive: true });
const vite = path.join(
  path.dirname(require.resolve("vite/package.json")),
  "bin/vite.js",
);
const server = spawn(
  process.execPath,
  [vite, "--host", "127.0.0.1", "--port", "1428", "--strictPort"],
  { cwd: path.join(root, "desktop"), windowsHide: true, stdio: "ignore" },
);
let browser;
(async () => {
  for (let attempt = 0; ; attempt++) {
    try {
      if ((await fetch("http://127.0.0.1:1428")).ok) break;
    } catch {}
    if (attempt > 80) throw new Error("UI preview did not start.");
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  browser = await chromium.launch({
    headless: true,
    executablePath: process.env.VOICEPROMPT_BROWSER_PATH || undefined,
  });
  const context = await browser.newContext({
    viewport: { width: 1120, height: 790 },
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("http://127.0.0.1:1428/?preview=1");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Settings", exact: true })
    .click();
  const updates = page.locator(".app-updates");
  await updates
    .getByRole("button", { name: "Check for updates", exact: true })
    .click();
  await expect(
    updates.getByRole("button", { name: "Update now", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".titlebar .update-shortcut")).toHaveText(
    "Update now",
  );
  await updates.scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(output, "available.png") });
  await updates
    .getByRole("button", { name: "Update now", exact: true })
    .click();
  await expect(updates.getByRole("progressbar")).toBeVisible();
  await updates
    .getByRole("button", { name: "Cancel download", exact: true })
    .click();
  await expect(
    updates.getByRole("button", { name: "Update now", exact: true }),
  ).toBeVisible();
  await updates
    .getByRole("button", { name: "Update now", exact: true })
    .click();
  await expect(
    updates.getByRole("button", { name: "Restart to update", exact: true }),
  ).toBeVisible();
  await updates.getByRole("button", { name: "Later", exact: true }).click();
  await expect(
    updates.getByRole("button", { name: "Restart to update", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: /^Microphone/ })
    .fill("Unsaved microphone");
  await updates
    .getByRole("button", { name: "Restart to update", exact: true })
    .click();
  await expect(page.locator(".toast")).toContainText("Save or discard");
  await page
    .getByRole("button", { name: "Save settings", exact: true })
    .first()
    .click();
  await updates
    .getByRole("button", { name: "Restart to update", exact: true })
    .click();
  await expect(page.locator(".toast")).toContainText(
    "would close, update, and reopen",
  );
  const automatic = updates.getByRole("checkbox", {
    name: /Check for updates automatically/,
  });
  await automatic.uncheck();
  await expect(automatic).not.toBeChecked();
  await automatic.check();
  for (const width of [1120, 800]) {
    await page.setViewportSize({ width, height: 790 });
    await updates.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, `ready-${width}.png`) });
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      "Update controls overflow the window",
    );
  }
  const accessibility = await new AxeBuilder({ page })
    .include(".app-updates")
    .analyze();
  assert.equal(
    accessibility.violations.length,
    0,
    JSON.stringify(accessibility.violations),
  );
  assert.deepEqual(errors, []);
  fs.writeFileSync(
    path.join(output, "report.json"),
    JSON.stringify(
      {
        mode: "explicit-sample-preview",
        checks: [
          "check",
          "availability",
          "titlebar-action",
          "download",
          "cancel",
          "ready",
          "later",
          "unsaved-settings-guard",
          "save-and-restart-action",
          "automatic-preference",
          "1120-and-800-layout",
          "accessibility",
        ],
        errors,
        accessibilityViolations: accessibility.violations,
      },
      null,
      2,
    ),
  );
  console.log(
    "Update UI checks passed: availability, download/cancel, restart guard, preferences, layout and accessibility.",
  );
})()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await browser?.close();
    server.kill();
  });
