/* Browser checks use an explicit sample mode. --cdp exercises the real native app. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawn, execFileSync } = require("node:child_process");
const { chromium, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;

const root = path.resolve(__dirname, "../..");
const out = path.join(root, ".impeccable/review");
fs.mkdirSync(out, { recursive: true });
fs.mkdirSync(path.join(root, "build"), { recursive: true });
const cdp = process.argv.indexOf("--cdp");
const native = cdp !== -1;
const report = {
  mode: native ? "native-webview-and-real-engine" : "explicit-sample-preview",
  checks: [],
  screenshots: [],
  accessibility: [],
};
let browser, server, main, island;
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(fn, timeout = 60000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    try {
      const value = await fn();
      if (value) return value;
    } catch {}
    await wait(250);
  }
  throw new Error("Timed out waiting for verification target.");
}
async function shot(page, name) {
  await page.evaluate(() => document.fonts.ready);
  await wait(240);
  const filename = path.join(out, `${native ? "native-" : ""}${name}.png`);
  await page.screenshot({ path: filename });
  report.screenshots.push(path.relative(root, filename));
}
async function navigate(name) {
  await main
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("button", { name, exact: true })
    .click();
  await expect(
    main.getByRole("heading", { name, exact: true }).first(),
  ).toBeVisible();
}
async function rpc(method, params = {}) {
  return main.evaluate(
    ({ method, params }) =>
      window.__TAURI_INTERNALS__.invoke("engine_request", { method, params }),
    { method, params },
  );
}
async function expand(tab) {
  if (await island.locator(".island-capsule").isVisible())
    await island.locator(".island-capsule").click();
  else if (
    await island
      .getByRole("button", { name: "Open notifications", exact: true })
      .isVisible()
  )
    await island
      .getByRole("button", { name: "Open notifications", exact: true })
      .click();
  await island.getByRole("tab", { name: new RegExp(`^${tab}`) }).click();
}

(async () => {
  if (native) {
    browser = await chromium.connectOverCDP(process.argv[cdp + 1]);
    main = await until(() =>
      browser
        .contexts()
        .flatMap((context) => context.pages())
        .find(
          (page) =>
            page.url().includes("tauri.localhost") &&
            !page.url().includes("surface=island"),
        ),
    );
    island = await until(() =>
      browser
        .contexts()
        .flatMap((context) => context.pages())
        .find((page) => page.url().includes("surface=island")),
    );
  } else {
    const vite = path.join(
      path.dirname(require.resolve("vite/package.json")),
      "bin/vite.js",
    );
    server = spawn(
      process.execPath,
      [vite, "--host", "127.0.0.1", "--port", "1426", "--strictPort"],
      { cwd: path.join(root, "desktop"), windowsHide: true, stdio: "ignore" },
    );
    await until(async () => (await fetch("http://127.0.0.1:1426")).ok);
    browser = await chromium.launch({
      headless: true,
      executablePath: process.env.VOICEPROMPT_BROWSER_PATH || undefined,
    });
    const context = await browser.newContext({
      viewport: { width: 1120, height: 790 },
      timezoneId: "Asia/Kolkata",
    });
    main = await context.newPage();
    await main.goto("http://127.0.0.1:1426/?preview=1");
  }
  const errors = [];
  main.on("pageerror", (error) => errors.push(error.message));
  await expect(
    main.getByRole("heading", { name: "Dictation", exact: true }),
  ).toBeVisible({ timeout: 60000 });
  if (native) {
    const state = await rpc("bootstrap");
    assert.equal(state.version, 1);
    assert.equal(state.runtime.acceptanceProfile, true);
    assert.deepEqual(state.credentials, { gemini: false, openrouter: false });
    report.checks.push(
      "Actual packaged bridge and isolated profile bootstrapped",
    );
  }
  for (const name of [
    "Dictation",
    "History",
    "Tasks",
    "Focus timer",
    "Alarms",
    "Contests",
    "Settings",
  ]) {
    await navigate(name);
    await shot(main, name.toLowerCase().replaceAll(" ", "-"));
    const result = await new AxeBuilder({ page: main })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    const failures = result.violations.filter((v) =>
      ["serious", "critical"].includes(v.impact),
    );
    report.accessibility.push({
      page: name,
      violations: failures.map((v) => ({
        id: v.id,
        impact: v.impact,
        targets: v.nodes.map((n) => n.target),
      })),
    });
    assert.equal(
      failures.length,
      0,
      `${name}: ${JSON.stringify(failures.map((v) => v.id))}`,
    );
  }
  report.checks.push(
    "All seven screens render and pass serious/critical WCAG checks",
  );
  await navigate("Tasks");
  await main
    .getByRole("textbox", { name: "New task", exact: true })
    .fill("Bridge verification task");
  await main.getByRole("button", { name: "Add task", exact: true }).click();
  await expect(
    main.getByText("Bridge verification task", { exact: true }),
  ).toBeVisible();
  await main
    .getByRole("button", { name: "Edit Bridge verification task", exact: true })
    .click();
  const editor = main.getByRole("dialog");
  await editor
    .getByRole("textbox", { name: "Notes", exact: true })
    .fill("Persistent verification note");
  await editor.getByRole("button", { name: "Save task", exact: true }).click();
  await expect(
    main.getByText("Persistent verification note", { exact: true }),
  ).toBeVisible();
  await main
    .getByRole("button", {
      name: "Complete Bridge verification task",
      exact: true,
    })
    .click();
  await expect(
    main.getByRole("button", {
      name: "Reopen Bridge verification task",
      exact: true,
    }),
  ).toBeVisible();
  report.checks.push(
    "Task create, edit and completion persist through service actions",
  );
  await navigate("Focus timer");
  await main
    .getByRole("spinbutton", { name: "Duration (minutes)", exact: true })
    .fill("2");
  await main
    .getByRole("button", { name: "Start focus session", exact: true })
    .click();
  await expect(
    main.getByRole("button", { name: "Pause", exact: true }),
  ).toBeVisible();
  if (native) {
    await expand("Focus");
    await island.getByRole("button", { name: "Pause", exact: true }).click();
    await expect(
      main.getByRole("button", { name: "Resume", exact: true }),
    ).toBeVisible();
    await island.getByRole("button", { name: "Resume", exact: true }).click();
    await expect(
      main.getByRole("button", { name: "Pause", exact: true }),
    ).toBeVisible();
    await shot(island, "island-focus");
    await island
      .getByRole("button", { name: "Collapse island", exact: true })
      .click();
  } else {
    await main.getByRole("button", { name: "Pause", exact: true }).click();
    await main.getByRole("button", { name: "Resume", exact: true }).click();
  }
  await main.getByRole("button", { name: "End session", exact: true }).click();
  await main
    .getByRole("dialog")
    .getByRole("button", { name: "End session", exact: true })
    .click();
  await expect(
    main.getByText("Ready when you are", { exact: true }),
  ).toBeVisible();
  report.checks.push(
    native
      ? "Main app and island share timer pause/resume/end state"
      : "Timer pause/resume/end controls work in explicit preview",
  );
  await navigate("Alarms");
  await main.getByRole("button", { name: "Add alarm", exact: true }).click();
  await main
    .getByRole("dialog")
    .getByRole("textbox", { name: "Alarm name", exact: true })
    .fill("Bridge verification alarm");
  await main
    .getByRole("dialog")
    .getByRole("button", { name: "Save alarm", exact: true })
    .click();
  const alarmToggle = main.getByRole("checkbox", {
    name: "Enable Bridge verification alarm",
    exact: true,
  });
  await expect(alarmToggle).toBeChecked();
  await alarmToggle.uncheck();
  await expect(alarmToggle).not.toBeChecked();
  report.checks.push("Alarm creation and enable/disable controls work");
  if (native) {
    await rpc("planner.task.save", {
      title: "Due bridge reminder",
      due: Date.now() / 1000 - 1,
    });
    const python = process.env.VOICEPROMPT_PYTHON || "python";
    execFileSync(
      python,
      [
        "-c",
        "import sqlite3,json,time,sys; c=sqlite3.connect(sys.argv[1]); r=c.execute(\"SELECT data FROM items WHERE kind='contest' AND id='acceptance-contest'\").fetchone(); d=json.loads(r[0]); d.update(start=time.time()+600,end=time.time()+7800); c.execute(\"UPDATE items SET data=? WHERE kind='contest' AND id='acceptance-contest'\",(json.dumps(d),)); c.commit(); c.close()",
        path.join(process.env.VOICEPROMPT_ACCEPTANCE_DIR, "planner.sqlite3"),
      ],
      { windowsHide: true },
    );
    await until(async () =>
      (await rpc("planner.snapshot")).notifications.some(
        (n) => n.kind === "contest",
      ),
    );
    await expand("Notifications");
    await expect(
      island.getByText("Acceptance Codeforces round", { exact: true }),
    ).toBeVisible();
    await expect(
      island.getByRole("button", { name: "Open contest", exact: true }),
    ).toBeVisible();
    await expect(
      island.getByText("Due bridge reminder", { exact: true }),
    ).toBeVisible();
    await shot(island, "island-notifications");
    const taskNotice = (await rpc("planner.snapshot")).notifications.find(
      (n) => n.title === "Due bridge reminder",
    );
    await rpc("planner.notification.act", {
      id: taskNotice.id,
      revision: taskNotice.revision,
      snooze: true,
    });
    assert(
      !(await rpc("planner.snapshot")).notifications.some(
        (n) => n.id === taskNotice.id,
      ),
    );
    await island
      .getByRole("button", { name: "Collapse island", exact: true })
      .click();
    await main.evaluate(() =>
      window.__TAURI_INTERNALS__.invoke("island_view", {
        mode: "compact",
        focus: false,
      }),
    );
    const focused = await main.evaluate(() =>
      window.__TAURI_INTERNALS__.invoke("plugin:window|is_focused", {
        label: "overlay",
      }),
    );
    assert.equal(focused, false);
    report.checks.push(
      "Contest and task reminders reach native island; snooze and nonactivating compact state verified",
    );
    const state = await rpc("planner.snapshot");
    assert(state.tasks.some((t) => t.notes === "Persistent verification note"));
  } else {
    island = await main.context().newPage();
    await island.goto(
      "http://127.0.0.1:1426/?preview=1&surface=island&panel=focus",
    );
    await expect(
      island.getByRole("tab", { name: "Focus", exact: true }),
    ).toBeVisible();
    await shot(island, "island-focus");
    await island.getByRole("tab", { name: /^Notifications/ }).click();
    await expect(
      island.getByText("Codeforces round", { exact: true }),
    ).toBeVisible();
    await shot(island, "island-notifications");
  }
  if (!native) {
    await main.setViewportSize({ width: 800, height: 560 });
    await navigate("Dictation");
    await shot(main, "minimum");
    assert(
      await main.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    await main.setViewportSize({ width: 390, height: 844 });
    await shot(main, "mobile");
    await main.setViewportSize({ width: 1120, height: 790 });
    await main.goto("http://127.0.0.1:1426/?preview=1&state=recording");
    await expect(main.getByText("Listening", { exact: true })).toBeVisible();
    await shot(main, "desktop");
  }
  assert.equal(
    errors.length,
    0,
    `Uncaught renderer errors: ${errors.join("; ")}`,
  );
  report.checks.push("No uncaught renderer errors");
  report.passed = true;
})()
  .catch((error) => {
    report.passed = false;
    report.error = error.stack || String(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    if (browser) await browser.close().catch(() => {});
    if (server) server.kill();
    fs.writeFileSync(
      path.join(
        root,
        "build",
        native ? "native-checks.json" : "ui-checks.json",
      ),
      JSON.stringify(report, null, 2),
    );
    console.log(JSON.stringify(report, null, 2));
  });
