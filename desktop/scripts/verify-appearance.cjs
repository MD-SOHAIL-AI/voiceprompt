const assert = require("node:assert/strict");
const { expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;

module.exports = async function verifyAppearance({
  main,
  island,
  native,
  rpc,
  report,
  shot,
  expand,
}) {
  const settings = () =>
    main
      .getByRole("navigation", { name: "Main navigation" })
      .getByRole("button", { name: "Settings", exact: true })
      .click();
  await settings();
  const show = main.getByRole("checkbox", {
    name: "Show floating island",
    exact: true,
  });
  const pin = main.getByRole("checkbox", {
    name: "Keep island visible",
    exact: true,
  });
  await show.check();
  await pin.check();
  report.themes = [];
  for (const palette of [
    "Black",
    "Forest",
    "Graphite",
    "Ocean",
    "Lavender",
    "Sand",
  ]) {
    await main.getByText(palette, { exact: true }).click();
    for (const appearance of ["Light", "Dark"]) {
      await main.getByText(appearance, { exact: true }).click();
      for (const page of [main, island]) {
        await expect(page.locator("html")).toHaveAttribute(
          "data-palette",
          palette.toLowerCase(),
        );
        await expect(page.locator("html")).toHaveAttribute(
          "data-appearance",
          appearance.toLowerCase(),
        );
      }
      const contrast = await main.evaluate(() => {
        const style = getComputedStyle(document.documentElement);
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = 1;
        const ctx = canvas.getContext("2d");
        function rgb(token) {
          ctx.fillStyle = style.getPropertyValue(`--${token}`).trim();
          ctx.fillRect(0, 0, 1, 1);
          return [...ctx.getImageData(0, 0, 1, 1).data].slice(0, 3);
        }
        function luminanceRGB(channels) {
          const [r, g, b] = channels.map((x) => {
            const c = x / 255;
            return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
          });
          return 0.2126 * r + 0.7152 * g + 0.0722 * b;
        }
        function luminance(token) {
          return luminanceRGB(rgb(token));
        }
        const failures = [];
        function check(fg, bg, minimum) {
          const a = luminance(fg),
            b = luminance(bg);
          const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
          if (ratio < minimum) failures.push({ fg, bg, ratio, minimum });
        }
        for (const bg of [
          "background",
          "rail",
          "surface",
          "input",
          "island",
          "hover",
          "selected",
        ]) {
          check("text", bg, 4.5);
          check("muted", bg, 4.5);
        }
        for (const bg of ["background", "surface", "input", "island"]) {
          check("accent", bg, 4.5);
          check("button-border", bg, 3);
        }
        check("accent-ink", "accent", 4.5);
        check("amber", "warning-bg", 4.5);
        check("amber-ink", "amber", 4.5);
        check("danger", "danger-bg", 4.5);
        // At maximum transparency, test text and status glyphs against both
        // extremes of the desktop behind the island. Translucent secondary
        // text uses the stronger text token; controls retain opaque fills.
        for (const desktop of [0, 255]) {
          const bg = luminanceRGB(
            rgb("island").map((c) => c * 0.75 + desktop * 0.25),
          );
          for (const [fg, minimum] of [
            ["text", 4.5],
            ["accent", 3],
            ["amber", 3],
          ]) {
            const color = luminance(fg);
            const ratio =
              (Math.max(color, bg) + 0.05) / (Math.min(color, bg) + 0.05);
            if (ratio < minimum)
              failures.push({
                fg,
                bg: `25% transparent over ${desktop}`,
                ratio,
                minimum,
              });
          }
        }
        return failures;
      });
      assert.deepEqual(
        contrast,
        [],
        `${palette} ${appearance}: ${JSON.stringify(contrast)}`,
      );
      const a11y = await new AxeBuilder({ page: main })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze();
      const violations = a11y.violations.filter((v) =>
        ["serious", "critical"].includes(v.impact),
      );
      assert.equal(
        violations.length,
        0,
        `${palette} ${appearance}: ${JSON.stringify(violations.map((v) => ({ id: v.id, targets: v.nodes.map((n) => n.target) })))}`,
      );
      report.themes.push({
        palette,
        appearance,
        contrast: "passed",
        accessibility: "passed",
      });
      await shot(
        main,
        `appearance-${palette.toLowerCase()}-${appearance.toLowerCase()}`,
      );
    }
  }
  // The native window stays transparent; only the surface fill changes, never text opacity.
  const transparency = main.getByRole("slider", {
    name: /^Island transparency/,
  });
  await transparency.focus();
  await transparency.press("End");
  await expect(transparency).toHaveValue("25");
  for (const page of [main, island]) {
    await expect(page.locator("html")).toHaveAttribute(
      "data-island-translucent",
      "true",
    );
    assert.equal(
      await page.evaluate(() =>
        getComputedStyle(document.documentElement)
          .getPropertyValue("--island-opacity")
          .trim(),
      ),
      "75%",
    );
  }
  // Keyboard selection, saved choices, and the island's independently loaded document.
  await main.getByRole("radio", { name: "Light", exact: true }).focus();
  await main.getByRole("radio", { name: "Light", exact: true }).press("Space");
  await main.getByText("Ocean", { exact: true }).click();
  await main.reload();
  await expect(main.locator("html")).toHaveAttribute("data-palette", "ocean");
  await expect(main.locator("html")).toHaveAttribute(
    "data-appearance",
    "light",
  );
  await settings();
  await expect(pin).toBeChecked();
  await expect(transparency).toHaveValue("25");
  await island.reload();
  await expect(island.locator("html")).toHaveAttribute(
    "data-appearance",
    "light",
  );
  await expect(island.locator("html")).toHaveAttribute("data-palette", "ocean");
  await expand("Focus");
  await shot(island, "appearance-island-light");
  await expect(island.locator(".island-panel")).toHaveCSS("opacity", "1");
  await island
    .getByRole("button", { name: "Keep island visible", exact: true })
    .click();
  await expect(pin).not.toBeChecked();
  await pin.check();
  await show.uncheck();
  await expect(island.locator(".island-frame")).toHaveCount(0);
  if (native)
    await expect
      .poll(
        async () =>
          (
            await main.evaluate(() =>
              window.__TAURI_INTERNALS__.invoke("island_status"),
            )
          ).visible,
      )
      .toBe(false);
  await show.check();
  await expect(island.locator(".island-frame")).toHaveCount(1);
  if (native) {
    // Empty only the disposable acceptance profile to exercise the idle state.
    const hub = await rpc("planner.snapshot");
    for (const alarm of hub.alarms)
      await rpc("planner.delete", { kind: "alarm", id: alarm.id });
    for (const notice of (await rpc("planner.snapshot")).notifications)
      await rpc("planner.notification.act", {
        id: notice.id,
        revision: notice.revision,
      });
    await expect(island.getByText("Ready", { exact: true })).toBeVisible({
      timeout: 10000,
    });
    await pin.uncheck();
    await expect
      .poll(
        async () =>
          (
            await main.evaluate(() =>
              window.__TAURI_INTERNALS__.invoke("island_status"),
            )
          ).visible,
      )
      .toBe(false);
    await pin.check();
    await expect
      .poll(
        async () =>
          (
            await main.evaluate(() =>
              window.__TAURI_INTERNALS__.invoke("island_status"),
            )
          ).visible,
      )
      .toBe(true);
    const focus = await main.evaluate(() =>
      window.__TAURI_INTERNALS__.invoke("island_status"),
    );
    assert.equal(focus.foreground, false);
    assert.equal(focus.keyboardFocus, false);
    report.checks.push(
      "Pinned idle island stays visible without taking focus; auto-hide and explicit hide/reveal work",
    );
  }
  await main.getByText("System", { exact: true }).click();
  for (const colorScheme of ["light", "dark"]) {
    await Promise.all([
      main.emulateMedia({ colorScheme }),
      island.emulateMedia({ colorScheme }),
    ]);
    for (const page of [main, island])
      await expect(page.locator("html")).toHaveAttribute(
        "data-appearance",
        colorScheme,
      );
  }
  await Promise.all([
    main.emulateMedia({ colorScheme: null }),
    island.emulateMedia({ colorScheme: null }),
  ]);
  await main.getByText("Black", { exact: true }).click();
  await main.getByText("Dark", { exact: true }).click();
  await shot(island, "appearance-island-black-translucent");
  await transparency.focus();
  await transparency.press("Home");
  await expect(transparency).toHaveValue("0");
  await pin.uncheck();
  report.checks.push(
    "Twelve theme variants pass contrast and accessibility; keyboard, System changes, persistence, user-controlled transparency and two-window synchronization verified",
  );
};
