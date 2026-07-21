import { mkdtempSync, writeFileSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawn } from "node:child_process";

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function valueFor(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] ?? fallback : fallback;
}

function chromeBinary() {
  if (process.env.CHROME_BIN) return process.env.CHROME_BIN;
  return [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ].find((candidate) => {
    return existsSync(candidate);
  });
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status} from ${url}`);
  return response.json();
}

async function waitForJson(url, predicate, timeout = 15000) {
  const deadline = Date.now() + timeout;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const value = await getJson(url);
      if (predicate(value)) return value;
    } catch (error) {
      lastError = error;
    }
    await sleep(100);
  }
  throw new Error(`timed out waiting for ${url}: ${lastError?.message ?? "no matching target"}`);
}

class CdpClient {
  constructor(webSocketUrl) {
    this.socket = new WebSocket(webSocketUrl);
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();
  }

  async connect() {
    await new Promise((resolve, reject) => {
      this.socket.addEventListener("open", resolve, { once: true });
      this.socket.addEventListener("error", reject, { once: true });
    });
    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(message.error.message));
        else resolve(message.result);
        return;
      }
      const callbacks = this.listeners.get(message.method) ?? [];
      for (const callback of callbacks) callback(message.params ?? {});
    });
  }

  on(method, callback) {
    const callbacks = this.listeners.get(method) ?? [];
    callbacks.push(callback);
    this.listeners.set(method, callbacks);
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    this.socket.close();
  }
}

async function evaluate(client, expression) {
  const result = await client.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.exception?.description ?? "Runtime evaluation failed");
  }
  return result.result?.value;
}

function keyDetails(key) {
  const known = {
    Space: { key: " ", code: "Space", windowsVirtualKeyCode: 32 },
    Enter: { key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 },
    ArrowUp: { key: "ArrowUp", code: "ArrowUp", windowsVirtualKeyCode: 38 },
    ArrowDown: { key: "ArrowDown", code: "ArrowDown", windowsVirtualKeyCode: 40 },
    ArrowLeft: { key: "ArrowLeft", code: "ArrowLeft", windowsVirtualKeyCode: 37 },
    ArrowRight: { key: "ArrowRight", code: "ArrowRight", windowsVirtualKeyCode: 39 },
  };
  return known[key] ?? { key, code: key, windowsVirtualKeyCode: key.length === 1 ? key.toUpperCase().charCodeAt(0) : 0 };
}

async function pressKey(client, key) {
  const details = keyDetails(key);
  await client.send("Input.dispatchKeyEvent", { type: "rawKeyDown", ...details });
  await client.send("Input.dispatchKeyEvent", { type: "keyUp", ...details });
}

function keysFromControls(controls) {
  if (!controls) return [];
  if (typeof controls === "string") return [controls];
  if (Array.isArray(controls)) return controls.filter((value) => typeof value === "string");
  if (typeof controls.key === "string") return [controls.key];
  if (Array.isArray(controls.keys)) return controls.keys.filter((value) => typeof value === "string");
  if (typeof controls.primary?.key === "string") return [controls.primary.key];
  return [];
}

async function main() {
  const url = valueFor("--url");
  const screenshotPath = valueFor("--screenshot");
  const resultPath = valueFor("--result");
  const binary = chromeBinary();
  if (!url) throw new Error("--url is required");
  if (!binary) throw new Error("Chrome not found; set CHROME_BIN");

  const userDataDir = mkdtempSync(join(tmpdir(), "vibe-check-chrome-"));
  const port = 10000 + Math.floor(Math.random() * 40000);
  const chrome = spawn(binary, [
    "--headless=new",
    "--disable-gpu",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-extensions",
    "--hide-scrollbars",
    "--no-first-run",
    "--no-default-browser-check",
    "--remote-debugging-address=127.0.0.1",
    `--remote-debugging-port=${port}`,
    "--user-data-dir=" + userDataDir,
    "--window-size=1280,720",
    url,
  ], { stdio: ["ignore", "ignore", "pipe"] });

  let browser = null;
  let client = null;
  const consoleErrors = [];
  const pageErrors = [];
  const requests = [];
  const externalRequests = [];
  try {
    browser = await waitForJson(`http://127.0.0.1:${port}/json/version`, () => true);
    const targets = await waitForJson(`http://127.0.0.1:${port}/json/list`, (items) => items.some((item) => item.type === "page"));
    const page = targets.find((item) => item.type === "page");
    client = new CdpClient(page.webSocketDebuggerUrl);
    await client.connect();
    client.on("Runtime.consoleAPICalled", (event) => {
      const text = event.args?.map((arg) => arg.value ?? arg.description ?? "").join(" ") ?? "";
      if (event.type === "error" || event.type === "assert") consoleErrors.push(text);
    });
    client.on("Runtime.exceptionThrown", (event) => {
      pageErrors.push(event.exceptionDetails?.exception?.description ?? "uncaught exception");
    });
    client.on("Network.requestWillBeSent", (event) => {
      requests.push(event.request.url);
      try {
        const parsed = new URL(event.request.url);
        const local = parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost";
        if (!local && !["data:", "blob:", "chrome-extension:"].some((scheme) => event.request.url.startsWith(scheme))) {
          externalRequests.push(event.request.url);
        }
      } catch {
        externalRequests.push(event.request.url);
      }
    });
    await client.send("Runtime.enable");
    await client.send("Page.enable");
    await client.send("Network.enable");
    await client.send("Page.navigate", { url });
    await sleep(700);

    const before = await evaluate(client, `(() => {
      const seam = window.__GAME_TEST__;
      return {
        title: document.title,
        text: document.body?.innerText ?? "",
        ready: Boolean(seam?.ready?.()),
        finished: Boolean(seam?.isFinished?.()),
        controls: seam?.getControls?.() ?? null,
      };
    })()`);

    if (before?.ready && before?.controls) {
      const keys = keysFromControls(before.controls);
      if (keys.length > 0) {
        for (let round = 0; round < 12 && !(await evaluate(client, "Boolean(window.__GAME_TEST__?.isFinished?.())")); round += 1) {
          for (const key of keys) await pressKey(client, key);
          await sleep(40);
        }
      } else {
        await evaluate(client, "document.querySelector('button,[role=button],[data-game-action]')?.click()");
      }
    }

    const finishedAfterControls = Boolean(await evaluate(client, "Boolean(window.__GAME_TEST__?.isFinished?.())"));
    let replayFinished = false;
    if (before?.ready && await evaluate(client, "typeof window.__GAME_TEST__?.reset === 'function'")) {
      await evaluate(client, "window.__GAME_TEST__.reset()");
      await sleep(50);
      replayFinished = Boolean(await evaluate(client, "Boolean(window.__GAME_TEST__?.isFinished?.())"));
    }

    const afterReset = await evaluate(client, `(() => {
      const seam = window.__GAME_TEST__;
      return {
        ready: Boolean(seam?.ready?.()),
        finished: Boolean(seam?.isFinished?.()),
        state: seam?.getState?.() ?? null,
      };
    })()`);
    const surface = await evaluate(client, `(() => {
      const element = document.querySelector('[data-game-root], #game, canvas, main');
      if (!element) return null;
      const rect = element.getBoundingClientRect();
      if (!rect.width || !rect.height) return null;
      return {
        x: Math.max(0, rect.x),
        y: Math.max(0, rect.y),
        width: rect.width,
        height: rect.height,
        scale: 1,
      };
    })()`);
    let screenshot = null;
    if (screenshotPath) {
      const image = await client.send(
        "Page.captureScreenshot",
        surface ? { format: "png", captureBeyondViewport: false, clip: surface } : { format: "png" },
      );
      writeFileSync(screenshotPath, Buffer.from(image.data, "base64"));
      screenshot = screenshotPath;
    }
    const result = {
      ok: Boolean(before?.ready && finishedAfterControls && afterReset?.ready && !consoleErrors.length && !pageErrors.length && !externalRequests.length),
      ready: Boolean(before?.ready),
      finished: finishedAfterControls,
      replay_reset_observed: before?.ready && afterReset?.ready,
      replay_finished_before_reset: replayFinished,
      title: before?.title ?? "",
      body_text: before?.text ?? "",
      controls: before?.controls ?? null,
      state_after_reset: afterReset?.state ?? null,
      console_errors: consoleErrors,
      page_errors: pageErrors,
      requests,
      external_requests: externalRequests,
      screenshot_surface: surface,
      screenshot,
    };
    if (resultPath) writeFileSync(resultPath, JSON.stringify(result, null, 2) + "\n");
    process.stdout.write(JSON.stringify(result));
  } finally {
    try { await client?.send("Browser.close"); } catch {}
    client?.close();
    if (!chrome.killed) chrome.kill("SIGTERM");
    await sleep(100);
    try { rmSync(userDataDir, { recursive: true, force: true }); } catch {}
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack ?? error}\n`);
  process.stdout.write(JSON.stringify({ ok: false, error: String(error.message ?? error) }));
  process.exitCode = 1;
});
