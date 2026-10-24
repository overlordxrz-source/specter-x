/* Offline NODE JSONL -> unchanged WORLD v2 interface check. No device access. */
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const assert = require("node:assert/strict");

(async () => {
  const url = process.env.WORLD_URL;
  if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(url || ""))
    throw Error("WORLD_URL must be a loopback URL");
  const expectedCount = Number(process.env.NODE_COUNT || 7290);
  assert(Number.isInteger(expectedCount) && expectedCount >= 3);
  const selected = [0, Math.floor(expectedCount / 2), expectedCount - 1];
  const records = new Map();
  let count = 0;
  for await (const line of readline.createInterface({
    input: fs.createReadStream(process.env.NODE_CAPTURE),
  })) {
    if (selected.includes(count)) records.set(count, JSON.parse(line));
    count++;
  }
  assert.equal(count, expectedCount);
  const output = process.env.WORLD_SCREENSHOTS || "/tmp/node-world-verification";
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.WORLD_CHROMIUM
      ? { executablePath: process.env.WORLD_CHROMIUM } : {}),
  });
  const checks = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1512, height: 982 } });
    await page.goto(url);
    await page.locator("#jump-record").waitFor();
    for (const [index, expected] of records) {
      const direct = await (await fetch(url + "/api/state?index=" + index)).json();
      assert.equal(direct.status, "READY");
      assert.deepEqual(direct.observation, expected);
      assert.equal(direct.count, count);
      assert.equal(direct.mode, "REPLAY");
      assert.equal(direct.live_verified, false);
      await page.locator("#jump-record").fill(String(index + 1));
      await page.getByRole("button", { name: "Apply record jump" }).click();
      await page.waitForFunction(
        (i) => document.querySelector("#timeline").value === String(i), index,
      );
      checks.push({ index, observation_id: expected.id, pass: true });
    }
    await page.screenshot({ path: path.join(output, "node-recording.png") });
    const result = { status: "PASS", count, checks, physical_port_opened: false };
    fs.writeFileSync(path.join(output, "node-interface.json"), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
