import { test, expect } from '@playwright/test';
import { createHash } from 'node:crypto';
import { writeFile } from 'node:fs/promises';
import { mutateGlb } from '../web/asset-fixture.mjs';

const origin = process.env.PROOF_ORIGIN ?? 'http://127.0.0.1:4173';
const prefix = `${origin}/street-scene-showcase/`;
const url = `${prefix}interactive/?capture=1`;
const manifestUrl = `${prefix}assets/interactive/scene-manifest.json`;
const snapshot = page => page.evaluate(() => window.__streetSceneCapture.snapshot());
const phase = page => page.evaluate(() => window.__streetSceneBoot?.phase);

function observe(page, { nativeMediaWarnings = false } = {}) {
  const errors = [], requests = [], warnings = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() !== 'error') return;
    const text = message.text();
    if (nativeMediaWarnings && message.location().url === ''
      && /^Button failed to load, iconName = (invalid|pip|airplay)-placard, layoutTraits = \[MacOSLayoutTraits Inline\], src = blob:/.test(text)
      && text.includes(`src = blob:${origin}/`)) {
      warnings.push({ message: text, location: message.location() });
    } else errors.push(text);
  });
  page.on('requestfailed', request => errors.push(`${request.url()}: ${request.failure()?.errorText}`));
  page.on('request', request => requests.push(request.url()));
  return { errors, requests, warnings };
}

async function ready(page) {
  await page.goto(url);
  await expect.poll(() => phase(page)).toBe('ready');
  await page.evaluate(() => window.__streetSceneCapture.ready);
}

async function failed(page, observed, expected) {
  await expect.poll(() => phase(page)).toBe('failed');
  await expect(page.locator('#video-fallback')).toBeVisible();
  await expect(page.locator('#reload')).toBeEnabled();
  for (const id of ['play', 'restart', 'inspect']) await expect(page.locator(`#${id}`)).toBeDisabled();
  expect(observed.errors.length).toBeGreaterThan(0);
  expect(observed.errors.every(error => expected.test(error)), observed.errors.join('\n')).toBe(true);
  if (await page.evaluate(() => !!window.__streetSceneCapture)) {
    await expect(page.evaluate(() => window.__streetSceneCapture.snapshot())).rejects.toThrow(/ready/);
  }
}

let assetPromise;
function asset() {
  assetPromise ??= (async () => {
    const manifest = await (await fetch(manifestUrl)).json();
    const bytes = Buffer.from(await (await fetch(`${prefix}assets/interactive/${manifest.asset.file}`)).arrayBuffer());
    return { manifest, bytes };
  })();
  return assetPromise;
}

async function replacedAsset(page, bytes) {
  const { manifest } = await asset();
  const changed = structuredClone(manifest);
  const sha256 = createHash('sha256').update(bytes).digest('hex');
  changed.asset = { sha256, file: `attempt-23.${sha256}.glb`, bytes: bytes.length };
  await page.route('**/scene-manifest.json', route => route.fulfill({ json: changed }));
  await page.route('**/*.glb', route => route.fulfill({ body: bytes, contentType: 'model/gltf-binary' }));
}

test('production prefix, existing pages, navigation and served files remain intact', async ({ page }) => {
  const observed = observe(page);
  for (const file of ['index.html', 'concept.html', 'attempts.html']) {
    await page.goto(`${prefix}${file}`);
    await expect(page.locator('h1')).toBeVisible();
    await expect(page.locator('nav a[href="interactive/index.html"]')).toBeVisible();
    await page.locator('img').evaluateAll(async images => {
      for (const image of images) image.loading = 'eager';
      await Promise.all(images.map(image => image.decode()));
    });
  }
  await ready(page);
  expect((await snapshot(page)).transport).toBe('paused');
  for (const target of ['/interactive/', '/assets/', '/THREEJS-IMPLEMENTATION-PLAN.md',
    '/%2e%2e/%2e%2e/etc/passwd', '/street-scene-showcase/%2e%2e/%2e%2e/etc/passwd']) {
    expect((await page.request.get(`${origin}${target}`)).status()).toBe(404);
  }
  for (const target of ['interactive/assets/viewer.js', 'interactive/assets/viewer.css',
    'assets/interactive/scene-manifest.json', 'assets/street-scene-attempt-23.mp4']) {
    expect((await page.request.get(`${prefix}${target}`)).ok()).toBe(true);
  }
  expect(observed.requests.filter(request => !request.startsWith(prefix) && !request.startsWith('blob:'))).toEqual([]);
  expect(observed.errors).toEqual([]);
});

test('play, pause, end, restart, keyboard inspection and repeated resources are coherent', async ({ page }) => {
  const observed = observe(page);
  await ready(page);
  const initial = await snapshot(page);
  await page.locator('#play').focus();
  await page.keyboard.press('Enter');
  await expect.poll(async () => (await snapshot(page)).seconds).toBeGreaterThan(0.1);
  await page.locator('#inspect').click();
  const inspected = await snapshot(page);
  expect(inspected.transport).toBe('paused');
  expect(inspected.mode).toBe('inspection');
  await expect(page.locator('#play')).toBeDisabled();
  await expect(page.locator('#restart')).toBeDisabled();
  const bounds = await page.locator('canvas').boundingBox();
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  await page.mouse.down();
  await page.mouse.move(bounds.x + bounds.width / 2 + 80, bounds.y + bounds.height / 2 + 15, { steps: 5 });
  await page.mouse.up();
  expect((await snapshot(page)).activeCameraPosition).not.toEqual(inspected.activeCameraPosition);
  expect((await snapshot(page)).cameraPosition).toEqual(inspected.cameraPosition);
  await page.keyboard.press('Escape');
  expect((await snapshot(page)).seconds).toBe(inspected.seconds);
  expect((await snapshot(page)).transport).toBe('paused');
  await page.evaluate(() => window.__streetSceneCapture.seek(5));
  await page.locator('#inspect').click();
  await page.locator('#inspect').click();
  expect((await snapshot(page)).transport).toBe('ended');
  await page.locator('#play').click();
  await expect.poll(async () => (await snapshot(page)).transport).toBe('playing');
  await page.locator('#play').click();
  expect((await snapshot(page)).transport).toBe('paused');
  for (let cycle = 0; cycle < 2; cycle++) {
    for (const seconds of [0, 2.5, 5]) {
      await page.evaluate(seconds => window.__streetSceneCapture.seek(seconds), seconds);
      await page.locator('#inspect').click();
      await page.locator('#inspect').click();
    }
  }
  const warm = (await snapshot(page)).resources;
  for (let cycle = 0; cycle < 5; cycle++) {
    await page.locator('#restart').click();
    await page.locator('#play').click();
    await page.locator('#inspect').click();
    await page.locator('#inspect').click();
  }
  expect((await snapshot(page)).resources).toEqual(warm);
  await page.evaluate(() => window.__streetSceneCapture.seek(0));
  expect((await snapshot(page)).cameraPosition).toEqual(initial.cameraPosition);
  expect(observed.errors).toEqual([]);
});

test('hidden-tab suspension remains paused when visible again', async ({ page }) => {
  const observed = observe(page);
  await ready(page);
  await page.locator('#play').click();
  await expect.poll(async () => (await snapshot(page)).seconds).toBeGreaterThan(0.05);
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  const paused = await snapshot(page);
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  expect((await snapshot(page)).transport).toBe('paused');
  expect((await snapshot(page)).seconds).toBe(paused.seconds);
  expect(observed.errors).toEqual([]);
});

for (const [width, height, dpr, mobile] of [
  [1280, 720, 1, false], [1920, 1080, 2, false], [390, 844, 3, true], [844, 390, 2, true],
]) {
  test(`uncropped layout ${width}x${height} DPR ${dpr}`, async ({ browser, browserName }, info) => {
    const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: dpr, isMobile: mobile, hasTouch: mobile });
    try {
      const page = await context.newPage();
      const observed = observe(page, { nativeMediaWarnings: browserName === 'webkit' && mobile });
      await ready(page);
      const value = await snapshot(page);
      expect(value.cssWidth / value.cssHeight).toBeCloseTo(16 / 9, 2);
      expect(value.dpr).toBe(mobile || value.cssWidth <= 640 ? 1 : Math.min(dpr, 1.5));
      expect(value.pixelWidth).toBe(Math.floor(value.cssWidth * value.dpr));
      expect(value.pixelHeight).toBe(Math.floor(value.cssHeight * value.dpr));
      expect(value.projection).toEqual((await asset()).manifest.expected.camera.projection.map((value, i) =>
        i === 0 || i === 5 || i === 10 || i === 14 ? expect.closeTo(value, 5) : value));
      await page.setViewportSize({ width: height, height: width });
      await expect.poll(async () => (await snapshot(page)).cssWidth).not.toBe(value.cssWidth);
      expect((await snapshot(page)).projection).toEqual(value.projection);
      expect(observed.errors).toEqual([]);
      if (observed.warnings.length) {
        info.annotations.push({ type: 'browser limitation',
          description: 'WebKit emulated native-video placard icon errors also reproduce on the unchanged final-video page.' });
        await info.attach('webkit-native-media-warnings', {
          body: JSON.stringify(observed.warnings, null, 2), contentType: 'application/json',
        });
      }
    } finally { await context.close(); }
  });
}

test('capture surface is absent without opt-in and fallback works without JavaScript', async ({ browser, page }) => {
  await page.goto(`${prefix}interactive/`);
  await expect.poll(() => phase(page)).toBe('ready');
  expect(await page.evaluate(() => '__streetSceneCapture' in window)).toBe(false);
  const context = await browser.newContext({ javaScriptEnabled: false });
  try {
    const staticPage = await context.newPage();
    await staticPage.goto(`${prefix}interactive/`);
    await expect(staticPage.locator('#video-fallback')).toBeVisible();
    await expect(staticPage.locator('noscript p')).toContainText('JavaScript is disabled');
    await expect(staticPage.locator('#scene-viewport')).toBeHidden();
    await expect(staticPage.locator('#video-fallback')).toBeInViewport();
    await expect(staticPage.locator('#play')).toBeDisabled();
    expect(await staticPage.locator('video source').getAttribute('src')).toContain('street-scene-attempt-23.mp4');
  } finally { await context.close(); }
});

for (const target of ['viewer.js', 'scene-manifest.json', '*.glb']) {
  test(`usable fallback for missing ${target}`, async ({ page }) => {
    const observed = observe(page);
    await page.route(`**/${target}`, route => route.fulfill({ status: 404, body: 'not found' }));
    await page.goto(url);
    await failed(page, observed, /404|not found|could not load|Failed to load|Scene request failed|Load failed|Importing a module|Failed to fetch dynamically imported module|net::ERR_ABORTED$|: cancelled$/i);
  });
}

for (const target of ['viewer.js', 'scene-manifest.json', '*.glb']) {
  test(`independent deadline covers stalled ${target} and late completion`, async ({ page }) => {
    const observed = observe(page);
    await page.clock.install();
    let pending;
    await page.route(`**/${target}`, route => { pending = route; });
    await page.goto(url, { waitUntil: 'commit' });
    await expect.poll(() => !!pending).toBe(true);
    await expect.poll(() => phase(page)).toBe('loading');
    if (target !== 'viewer.js') {
      await expect.poll(() => page.evaluate(() => !!window.__streetSceneCapture)).toBe(true);
      await expect(page.evaluate(() => window.__streetSceneCapture.snapshot())).rejects.toThrow(/ready/);
    }
    await page.clock.fastForward(120001);
    await failed(page, observed, /timed out|abort|cancel|Load failed|Failed to load/i);
    await pending.continue();
    await page.clock.fastForward(1000);
    expect(await phase(page)).toBe('failed');
    await page.unrouteAll();
    await page.reload();
    await expect.poll(() => phase(page)).toBe('ready');
  });
}

test('deadline covers a stalled model body without accepting a late body', async ({ page }) => {
  const observed = observe(page);
  await page.clock.install();
  await page.addInitScript(() => {
    const original = window.fetch;
    window.fetch = async (...args) => {
      const response = await original(...args);
      if (!String(args[0]).endsWith('.glb')) return response;
      const bytes = new Uint8Array(await response.arrayBuffer());
      return new Response(new ReadableStream({
        start(controller) { window.__releaseBody = () => { controller.enqueue(bytes); controller.close(); }; },
      }), { status: 200 });
    };
  });

  await page.goto(url, { waitUntil: 'commit' });
  await expect.poll(() => page.evaluate(() => typeof window.__releaseBody)).toBe('function');
  await page.clock.fastForward(120001);
  await failed(page, observed, /timed out|abort|cancel/i);
  await page.evaluate(() => window.__releaseBody());
  await page.clock.fastForward(1000);
  expect(await phase(page)).toBe('failed');
});

test('late image decode after failure closes every bitmap and cannot restore readiness', async ({ page }) => {
  const observed = observe(page);
  await page.clock.install();
  await page.addInitScript(() => {
    const decode = window.createImageBitmap.bind(window);
    const close = ImageBitmap.prototype.close;
    window.__decodeWaiters = [];
    window.__closedBitmaps = 0;
    ImageBitmap.prototype.close = function () { window.__closedBitmaps++; return close.call(this); };
    window.createImageBitmap = async (...args) => {
      const image = await decode(...args);
      return new Promise(resolve => window.__decodeWaiters.push(() => resolve(image)));
    };
  });
  await page.goto(url, { waitUntil: 'commit' });
  await expect.poll(() => page.evaluate(() => window.__decodeWaiters.length)).toBe(7);
  await page.clock.fastForward(120001);
  await failed(page, observed, /timed out|abort|cancel/i);
  await page.evaluate(() => window.__decodeWaiters.splice(0).forEach(resolve => resolve()));
  await expect.poll(() => page.evaluate(() => window.__closedBitmaps)).toBe(7);
  expect(await phase(page)).toBe('failed');
});

for (const failure of ['malformed', 'missing role', 'decoder', 'texture']) {
  test(`usable fallback for ${failure} with matching asset hash`, async ({ page }) => {
    const observed = observe(page);
    let bytes = Buffer.from((await asset()).bytes);
    if (failure === 'malformed') bytes = Buffer.from('malformed GLB');
    else if (failure === 'missing role') {
      bytes = mutateGlb(bytes, json => { json.nodes.find(node => node.name === 'WheelFL').name = 'Missing'; });
    } else {
      const length = bytes.readUInt32LE(12), json = JSON.parse(bytes.subarray(20, 20 + length));
      const view = failure === 'texture' ? json.bufferViews[json.images[0].bufferView]
        : json.bufferViews.find(view => view.extensions?.EXT_meshopt_compression).extensions.EXT_meshopt_compression;
      bytes[28 + length + (view.byteOffset ?? 0)] ^= 0xff;
    }
    await replacedAsset(page, bytes);
    await page.goto(url);
    await failed(page, observed, /GLB|role|buffer|decode|texture|bitmap|image|load|Meshopt|access|bounds/i);
  });
}

for (const failure of ['unavailable', 'lost during startup', 'lost after ready']) {
  test(`WebGL ${failure} produces a reload-only fallback`, async ({ page }) => {
    const observed = observe(page);
    if (failure !== 'lost after ready') {
      await page.addInitScript(failure => {
        const original = HTMLCanvasElement.prototype.getContext;
        HTMLCanvasElement.prototype.getContext = function (type, ...args) {
          if (type !== 'webgl2') return original.call(this, type, ...args);
          if (failure === 'unavailable') return null;
          const context = original.call(this, type, ...args);
          window.__lossPhase = window.__streetSceneBoot.phase;
          context.getExtension('WEBGL_lose_context').loseContext();
          return context;
        };
      }, failure);
      await page.goto(url);
    } else {
      await ready(page);
      await page.evaluate(() => document.querySelector('canvas').getContext('webgl2').getExtension('WEBGL_lose_context').loseContext());
    }
    await failed(page, observed, /WebGL|context|lost|Render/i);
    if (failure === 'lost during startup') expect(await page.evaluate(() => window.__lossPhase)).toBe('loading');
  });
}

test('three warmed hardware runs meet the exact desktop canvas performance gates', async ({ browser, browserName }, info) => {
  test.skip(browserName !== 'chromium', 'Desktop performance is measured on hardware-backed Chromium; WebKit covers correctness.');
  test.setTimeout(60000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, deviceScaleFactor: 1.5 });
  try {
    const page = await context.newPage(), observed = observe(page);
    const coldStart = performance.now();
    await ready(page);
    const coldStartupMs = performance.now() - coldStart;
    await page.addStyleTag({ content: 'main{max-width:none!important;width:1280px!important;padding:0!important;margin:0!important}#scene-viewport{width:1280px!important;height:720px!important}' });
    await expect.poll(async () => (await snapshot(page)).pixelWidth).toBe(1920);
    const before = await snapshot(page);
    expect([before.cssWidth, before.cssHeight, before.pixelWidth, before.pixelHeight, before.dpr]).toEqual([1280, 720, 1920, 1080, 1.5]);
    const gpu = await page.evaluate(() => {
      const gl = document.querySelector('canvas').getContext('webgl2'), ext = gl.getExtension('WEBGL_debug_renderer_info');
      return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'unavailable';
    });

    expect(gpu).not.toMatch(/SwiftShader|Software|llvmpipe|unavailable/i);
    await page.locator('#inspect').click();
    await page.locator('#inspect').click();
    const runs = [];
    for (let run = 0; run < 4; run++) {
      const result = await page.evaluate(() => new Promise(resolve => {
        document.querySelector('#restart').click();
        const initial = window.__streetSceneCapture.snapshot();
        const start = performance.now(), intervals = [];
        let previous = start, count = initial.completedFrames, maxMain = 0, maxShadow = 0;
        function sample() {
          const now = performance.now(), value = window.__streetSceneCapture.snapshot();
          if (value.completedFrames > count) {
            intervals.push(now - previous);
            previous = now;
            count = value.completedFrames;
            maxMain = Math.max(maxMain, value.mainDrawCalls);
            maxShadow = Math.max(maxShadow, value.shadowDrawCalls);
          }
          if (value.transport === 'ended') {
            const elapsedMs = now - start, ordered = [...intervals].sort((a, b) => a - b);
            resolve({ elapsedMs, frames: count - initial.completedFrames, sampleCount: intervals.length,
              fps: (count - initial.completedFrames) * 1000 / elapsedMs,
              medianMs: ordered[Math.floor(ordered.length / 2)], p95Ms: ordered[Math.ceil(ordered.length * 0.95) - 1],
              worstMs: ordered.at(-1), maxMain, maxShadow, resources: value.resources });
          } else requestAnimationFrame(sample);
        }
        requestAnimationFrame(sample);
      }));
      if (run) runs.push(result);
    }
    let complete = false;
    try {
      for (const run of runs) {
        expect(run.frames).toBeGreaterThanOrEqual(150);
        expect(run.fps).toBeGreaterThanOrEqual(30);
        expect(run.p95Ms).toBeLessThanOrEqual(50);
        expect(run.maxMain).toBeLessThanOrEqual(300);
        expect(run.resources).toEqual(runs[0].resources);
      }
      expect(observed.errors).toEqual([]);
      complete = true;
    } finally {
      await writeFile(info.outputPath('performance.json'), JSON.stringify({ complete, gpu, coldStartupMs, canvas: before, runs }, null, 2));
    }
  } finally { await context.close(); }
});

test('records the complete motion and restart boundary for visual inspection', async ({ browser, browserName }, info) => {
  test.skip(browserName !== 'chromium', 'One hardware Chromium recording supplies motion review; WebKit correctness is tested separately.');
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, deviceScaleFactor: 1,
    recordVideo: { dir: info.outputPath('recording'), size: { width: 1440, height: 1100 } } });
  let video, motion;
  try {
    const page = await context.newPage(), observed = observe(page);
    video = page.video();
    await ready(page);
    const first = await snapshot(page);
    await page.locator('#play').click();
    await expect.poll(async () => (await snapshot(page)).transport).toBe('ended');
    const last = await snapshot(page);
    expect(last.seconds).toBe(5);
    expect(last.heroPosition[2] - first.heroPosition[2]).toBeCloseTo(-17.5, 5);
    await page.locator('#restart').click();
    await expect.poll(async () => (await snapshot(page)).seconds).toBeGreaterThan(0.5);
    await page.locator('#play').click();
    const restarted = await snapshot(page);
    expect(restarted.transport).toBe('paused');
    expect(restarted.seconds).toBeLessThan(2);
    expect(observed.errors).toEqual([]);
    motion = { complete: true, first, last, restarted };
  } finally { await context.close(); }
  await video.saveAs(info.outputPath('motion-and-restart.webm'));
  await writeFile(info.outputPath('motion.json'), JSON.stringify(motion, null, 2));
});
