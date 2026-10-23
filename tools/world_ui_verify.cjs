/* Offline browser acceptance against an already-running local WORLD instance.
   npm install playwright as a development-only tool, then install chromium.
   WORLD_URL and WORLD_SCREENSHOTS select a local service and artifact directory.
   This test never opens physical sensors. */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
async function until(fn, ms = 10000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (await fn()) return;
    await new Promise((r) => setTimeout(r, 75));
  }
  throw Error("Condition timed out");
}
(async () => {
  const url = process.env.WORLD_URL;
  if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(url || ""))
    throw Error("WORLD_URL must be a loopback URL");
  const out = process.env.WORLD_SCREENSHOTS || "/tmp/world-ui";
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.WORLD_CHROMIUM
      ? { executablePath: process.env.WORLD_CHROMIUM }
      : {}),
  });
  const context = await browser.newContext({
    viewport: { width: 1512, height: 982 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let checks = [];
  const check = (name, value) => {
    assert(value, name);
    checks.push({ name, pass: true });
  };
  try {
    await page.goto(url);
    await page.locator(".metric .number").first().waitFor();
    await page
      .getByRole("button", { name: "Open session", exact: false })
      .click();
    await page.locator("#session-search").fill("no-such-capture-control");
    check(
      "Recording search excludes nonmatching files",
      (await page.locator("#session-list [data-session]").count()) === 0,
    );
    await page.locator("#session-search").fill("phase0-short");
    await page
      .locator("#session-list [data-session]")
      .filter({ hasText: "phase0-short.raw.csi" })
      .first()
      .click();
    await until(async () =>
      (await page.locator("#source-status").innerText()).startsWith("READY"),
    );
    check(
      "Replay mode labeled",
      (await page.locator("#mode").innerText()) === "REPLAY",
    );
    await page.locator("#timeline").focus();
    await page.locator("#timeline").press("End");
    await until(
      async () =>
        (await page.locator("#record-count").innerText()).split(" / ")[0] ===
        (await page.locator("#record-count").innerText()).split(" / ")[1],
    );
    await page.locator("#packet-history").waitFor();
    await until(
      async () =>
        (await page.locator("#packet-history").getAttribute("width")) === "160",
    );
    check(
      "History retains bounded actual packet window",
      (await page.locator("#packet-history").getAttribute("width")) === "160",
    );
    await page
      .locator("#packet-history")
      .hover({ position: { x: 100, y: 60 } });
    check(
      "History hover exposes real metadata",
      (await page.locator("#history-readout").innerText()).includes("PHY"),
    );
    await page
      .locator("#packet-history")
      .click({ position: { x: 100, y: 60 } });
    await page.locator("#inspection[open]").waitFor();
    check(
      "History opens source evidence",
      (await page.locator("#inspection-body").innerText()).includes("sha256"),
    );
    await page.locator("#close-inspection").click();
    await page.screenshot({ path: path.join(out, "world-overview-1512.png") });
    check(
      "Unavailable sources visible",
      await page
        .locator("#content")
        .innerText()
        .then((t) => t.includes("OFFLINE") && t.includes("UNAVAILABLE")),
    );
    await page.getByRole("button", { name: "Sensing", exact: true }).click();
    await page.locator("#source-filter").waitFor();
    await page.locator("#source-filter").selectOption("bench/di188/analog");
    await until(
      async () =>
        await page
          .getByText("No signal available", { exact: true })
          .isVisible(),
    );
    check(
      "Offline selection has no substituted chart",
      (await page.locator("svg").count()) === 0,
    );
    await page.locator("#source-filter").selectOption("");
    await page.locator(".signal-chart").first().waitFor();
    await page.locator("#record-filter").fill("impossible");
    await until(async () =>
      (await page.locator("tbody").innerText()).includes("No matching"),
    );
    check(
      "Record filtering changes actual rows",
      (await page.locator("tbody tr[data-index]").count()) === 0,
    );
    await page.locator("#record-filter").fill("");
    await until(
      async () => (await page.locator("tbody tr[data-index]").count()) > 0,
    );
    await page.locator("tbody tr[data-index]").first().click();
    await page.locator("#inspection[open]").waitFor();
    check(
      "Observation inspector contains provenance",
      await page
        .locator("#inspection-body")
        .innerText()
        .then((t) => t.includes("sha256") && t.includes("acquisition")),
    );
    await page.locator("#close-inspection").click();
    await page.locator("#timeline").focus();
    await page.locator("#timeline").press("Home");
    await until(async () =>
      (await page.locator("#record-count").innerText()).startsWith("1 /"),
    );
    await page
      .getByRole("button", { name: "Play replay", exact: true })
      .click();
    await until(
      async () =>
        !(await page.locator("#record-count").innerText()).startsWith("1 /"),
    );
    await page
      .getByRole("button", { name: "Pause replay", exact: true })
      .click();
    await page.locator("#page-title").click();
    const beforeStep = await page.locator("#record-count").innerText();
    await page.keyboard.press("ArrowRight");
    await until(
      async () =>
        (await page.locator("#record-count").innerText()) !== beforeStep,
    );
    check(
      "Keyboard stepping changes the selected record",
      (await page.locator("#record-count").innerText()) !== beforeStep,
    );
    await page.locator("#speed").selectOption("2");
    check(
      "Playback speed interaction",
      (await page.locator("#speed").inputValue()) === "2",
    );
    await page
      .getByRole("button", { name: "Spatial workspace", exact: true })
      .click();
    await page
      .getByRole("heading", { name: "Geometry must be earned." })
      .waitFor();
    check(
      "Navigation restores page heading",
      await page.evaluate(() => scrollY === 0),
    );
    check(
      "No invented spatial scene",
      (await page.locator("#content canvas,#content svg").count()) === 0,
    );
    await page.screenshot({ path: path.join(out, "world-spatial-1512.png") });
    await page
      .getByRole("button", { name: "Research & sessions", exact: true })
      .click();
    await page.locator("[data-evidence]").first().waitFor();
    await page.locator("[data-evidence]").first().click();
    await until(
      async () =>
        (await page.locator("#content pre").first().innerText()).length > 100,
    );
    check(
      "Real checkpoint reader opens",
      !(await page.locator("#content pre").first().innerText()).includes(
        "Select a report",
      ),
    );
    await page
      .getByRole("button", { name: "Node network", exact: true })
      .click();
    await page
      .getByRole("heading", { name: "Local research service" })
      .waitFor();
    check(
      "No remote nodes claimed",
      await page
        .locator("#content")
        .innerText()
        .then((t) => t.includes("PLANNED") && t.includes("Not established")),
    );
    await page
      .getByRole("button", { name: "Evidence & diagnostics", exact: true })
      .click();
    await page.locator("#content pre").waitFor();
    check(
      "Raw evidence trace visible",
      await page
        .locator("#content pre")
        .innerText()
        .then((t) => t.includes("raw") && t.includes("sha256")),
    );
    await page.screenshot({ path: path.join(out, "world-evidence-1512.png") });
    await page.getByRole("button", { name: "Overview", exact: true }).click();
    await page.getByRole("button", { name: "Detach", exact: true }).click();
    await until(async () =>
      (await page.locator("#source-status").innerText()).includes(
        "DISCONNECTED",
      ),
    );
    check("Detach disables playback", await page.locator("#play").isDisabled());
    await page
      .getByRole("button", { name: "Open session", exact: false })
      .click();
    await page.locator("#sessions-dialog[open]").waitFor();
    const recording = page
      .locator("#session-list [data-session]")
      .filter({ hasText: "phase0-short.raw.csi" })
      .first();
    await recording.click();
    await until(async () =>
      (await page.locator("#source-status").innerText()).startsWith("READY"),
    );
    check(
      "Session reopen reconnects replay",
      (await page.locator("#mode").innerText()) === "REPLAY",
    );
    await page.locator("#timeline").focus();
    await page.locator("#timeline").press("End");
    for (const [width, height, dpr] of [
      [1280, 800, 1],
      [1920, 1080, 2],
      [900, 700, 1],
    ]) {
      await page.setViewportSize({ width, height });
      check(
        `No horizontal overflow at ${width}`,
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth + 1,
        ),
      );
      check(
        `Controls visible at ${width}`,
        await page.locator("#play").isVisible(),
      );
      await page.screenshot({
        path: path.join(out, `world-overview-${width}.png`),
      });
    }
    async function openNamed(name) {
      await page
        .getByRole("button", { name: "Open session", exact: false })
        .click();
      const item = page
        .locator("#session-list [data-session]")
        .filter({ hasText: name })
        .first();
      await item.click();
    }
    const catalog = await page.request
      .get(url + "/api/catalog")
      .then((r) => r.json());
    check(
      "Catalog exposes completeness metadata",
      Array.isArray(catalog.items) &&
        typeof catalog.truncated === "boolean" &&
        Number.isInteger(catalog.limit),
    );
    const faultControls = catalog.items.some(
      (f) => f.name === "synthetic-control.observations.jsonl",
    );
    if (faultControls) {
      let releaseOld, oldFetched;
      const releasePromise = new Promise((r) => (releaseOld = r));
      const fetchedPromise = new Promise((r) => (oldFetched = r));
      await page.route(
        "**/api/state*",
        async (route) => {
          const response = await route.fetch();
          oldFetched();
          await releasePromise;
          await route.fulfill({ response });
        },
        { times: 1 },
      );
      await fetchedPromise;
      await openNamed("synthetic-control.observations.jsonl");
      check(
        "Source switch immediately disables scrubbing",
        await page.locator("#timeline").isDisabled(),
      );
      await page.evaluate(() => {
        window.sourceSwitchTrace = [];
        window.sourceSwitchObserver = new MutationObserver(() => {
          window.sourceSwitchTrace.push(
            document.querySelector("#source-status").textContent,
          );
        });
        window.sourceSwitchObserver.observe(
          document.querySelector("#source-status"),
          {
            childList: true,
            subtree: true,
            characterData: true,
          },
        );
      });
      releaseOld();
      await until(async () =>
        (await page.locator("#mode").innerText()).includes("SIMULATED"),
      );
      check(
        "Prior-session READY response never reappears",
        await page.evaluate(() => {
          window.sourceSwitchObserver.disconnect();
          return !window.sourceSwitchTrace.some(
            (text) =>
              text.includes("READY") && text.includes("phase0-short.raw.csi"),
          );
        }),
      );
      check(
        "Simulated origin remains explicit",
        !(await page.locator("#mode").innerText()).includes("LIVE"),
      );
      await openNamed("quality-control.raw.csi");
      await until(
        async () =>
          await page
            .locator("#content .error-banner")
            .innerText()
            .then((t) => t.includes("DATA QUALITY")),
      );
      check(
        "Malformed and missing data visible",
        await page
          .locator("#content .error-banner")
          .innerText()
          .then((t) => t.includes("1 malformed") && t.includes("1 missing")),
      );
      check(
        "Unreviewed source remains UNKNOWN",
        await page
          .locator("#mode")
          .innerText()
          .then((t) => t.includes("UNKNOWN")),
      );
      await openNamed("broken-control.raw.csi");
      await until(async () =>
        (await page.locator("#source-status").innerText()).includes("ERROR"),
      );
      check(
        "Broken source fails visibly",
        await page.locator("#play").isDisabled(),
      );
      await page.screenshot({ path: path.join(out, "world-error-900.png") });
      await openNamed("phase0-short.raw.csi");
      await until(async () =>
        (await page.locator("#source-status").innerText()).startsWith("READY"),
      );

      // A delayed observation inspector response must not open after a
      // source switch. This is separate from the delayed /api/state refresh
      // guard above.
      await page.getByRole("button", { name: "Overview", exact: true }).click();
      await page.locator("tbody tr[data-index]").first().waitFor();
      let releaseInspection, inspectionFetched;
      const inspectionRelease = new Promise((r) => (releaseInspection = r));
      const inspectionFetchedPromise = new Promise((r) => (inspectionFetched = r));
      await page.route(
        "**/api/state?index=*",
        async (route) => {
          const response = await route.fetch();
          inspectionFetched();
          await inspectionRelease;
          await route.fulfill({ response });
        },
        { times: 1 },
      );
      await page.locator("tbody tr[data-index]").first().click();
      await inspectionFetchedPromise;
      await openNamed("synthetic-control.observations.jsonl");
      releaseInspection();
      await page.waitForTimeout(200);
      check(
        "Prior-session inspection response never opens",
        (await page.locator("#inspection[open]").count()) === 0,
      );

      // A delayed evidence response must not replace the new session's
      // evidence reader.
      await page
        .getByRole("button", { name: "Research & sessions", exact: true })
        .click();
      await page.locator("[data-evidence]").nth(1).waitFor();
      let releaseEvidence, evidenceFetched, evidenceMarker;
      const evidenceRelease = new Promise((r) => (releaseEvidence = r));
      const evidenceFetchedPromise = new Promise((r) => (evidenceFetched = r));
      await page.route(
        "**/api/evidence?id=*",
        async (route) => {
          const response = await route.fetch();
          const data = await response.json();
          evidenceMarker = String(data.content || "").slice(0, 80);
          evidenceFetched();
          await evidenceRelease;
          await route.fulfill({ response });
        },
        { times: 1 },
      );
      await page.locator("[data-evidence]").nth(1).click();
      await evidenceFetchedPromise;
      await openNamed("synthetic-control.observations.jsonl");
      releaseEvidence();
      await page.waitForTimeout(200);
      check(
        "Prior-session evidence response never renders",
        !(await page.locator("#content").innerText()).includes(evidenceMarker),
      );

      // Existing evidence and the inspector must also disappear immediately
      // on a session switch, with no delayed network response involved.
      await openNamed("phase0-short.raw.csi");
      await until(async () =>
        (await page.locator("#source-status").innerText()).startsWith("READY"),
      );
      await page
        .getByRole("button", { name: "Research & sessions", exact: true })
        .click();
      await page.locator("[data-evidence]").first().click();
      await until(async () =>
        !(await page.locator("#content pre").first().innerText()).includes(
          "Select a report",
        ),
      );
      const oldEvidence = await page.locator("#content pre").first().innerText();
      await page.getByRole("button", { name: "Overview", exact: true }).click();
      await page.locator("tbody tr[data-index]").first().click();
      await page.locator("#inspection[open]").waitFor();
      // The modal blocks pointer clicks, so drive the session switch through
      // the DOM; openSession must close it and clear the evidence state.
      await page.evaluate(() => document.querySelector("#open-session").click());
      await page.locator("#sessions-dialog[open]").waitFor();
      await page.evaluate(() => {
        const button = [...document.querySelectorAll(
          "#session-list [data-session]",
        )].find((b) => b.textContent.includes("synthetic-control"));
        button.click();
      });
      await until(async () =>
        (await page.locator("#source-status").innerText()).startsWith("READY"),
      );
      check(
        "Previous inspection closes on session switch",
        (await page.locator("#inspection[open]").count()) === 0,
      );
      await page
        .getByRole("button", { name: "Research & sessions", exact: true })
        .click();
      const evidenceAfterSwitch = await page.locator("#content pre").first().innerText();
      check(
        "Previous evidence clears on session switch",
        !evidenceAfterSwitch.includes(oldEvidence.slice(0, 40)) &&
          evidenceAfterSwitch.includes("Select a report"),
      );
    }
    check("No browser runtime exceptions", errors.length === 0);
    const report = {
      status: "PASS",
      url,
      checks,
      browser: await browser.version(),
      playwright: require("playwright/package.json").version,
      hardware_access: false,
    };
    fs.writeFileSync(
      path.join(out, "ui-verification.json"),
      JSON.stringify(report, null, 2) + "\n",
    );
    console.log(JSON.stringify(report, null, 2));
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
