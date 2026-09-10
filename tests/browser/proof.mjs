import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium, webkit } from '@playwright/test';

if (!process.env.PROOF_OUTPUT) throw new Error('Set PROOF_OUTPUT to private task-owned staging');
const output = path.resolve(process.env.PROOF_OUTPUT);
await mkdir(output, { recursive: true });
const origin = process.env.PROOF_ORIGIN ?? 'http://127.0.0.1:4173';
const engine = process.env.PROOF_ENGINE === 'webkit' ? webkit : chromium;
const browser = await engine.launch({ headless: true,
  ...(process.env.PROOF_ENGINE === 'webkit' ? { executablePath: process.env.WEBKIT_EXECUTABLE }
    : process.env.PROOF_HARDWARE === '1' ? { channel: 'chromium', args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'] } : {}),
});
try {
  const page = await browser.newPage({ viewport: { width: 1920, height: 1400 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(`${message.text()} [${message.location().url}]`); });
  page.on('requestfailed', request => errors.push(`${request.url()}: ${request.failure()?.errorText}`));
  const start = performance.now();
  await page.goto(`${origin}/street-scene-showcase/interactive/?capture=1`);
  await page.addStyleTag({ content:
    'main{max-width:none!important;width:1920px!important;padding:0!important;margin:0!important}' +
    '#scene-viewport{width:1920px!important;height:1080px!important}' });
  await page.waitForFunction(() => window.__streetSceneBoot?.phase !== 'loading', null, { timeout: 125000 });
  const phase = await page.evaluate(() => window.__streetSceneBoot.phase);
  assert.equal(phase, 'ready', errors.join('\n'));
  await page.evaluate(() => window.__streetSceneCapture.ready);
  const coldStartupMs = performance.now() - start;
  const captures = [];
  for (const [frame, seconds] of [[1, 0], [61, 2.5], [120, 119 / 24]]) {
    const snapshot = await page.evaluate(seconds => {
      window.__streetSceneCapture.seek(seconds);
      window.__streetSceneCapture.renderOnce();
      return window.__streetSceneCapture.snapshot();
    }, seconds);
    assert.equal(snapshot.phase, 'ready');
    assert.equal(snapshot.rendered, true);
    assert.equal(snapshot.pixelWidth, 1920);
    assert.equal(snapshot.pixelHeight, 1080);
    assert.equal(snapshot.seconds, seconds);
    const image = await page.evaluate(() => {
      window.__streetSceneCapture.renderOnce();
      return document.querySelector('#scene-canvas').toDataURL('image/png');
    });
    const png = Buffer.from(image.split(',')[1], 'base64');
    assert.equal(png.readUInt32BE(16), 1920);
    assert.equal(png.readUInt32BE(20), 1080);
    await writeFile(path.join(output, `${frame}.png`), png);
    captures.push({ frame, ...snapshot });
  }
  for (const [seconds, anchor] of [[5, captures[2]], [2.5, captures[1]], [0, captures[0]]]) {
    const sampled = await page.evaluate(seconds => {
      window.__streetSceneCapture.seek(seconds);
      window.__streetSceneCapture.renderOnce();
      return window.__streetSceneCapture.snapshot();
    }, seconds);
    for (const key of ['heroPosition', 'cameraPosition', 'projection']) {
      assert.ok(sampled[key].every((value, index) => Math.abs(value - anchor[key][index]) < 1e-6),
        `${key} failed backward/final-hold sampling at ${seconds}`);
    }
    await page.locator('#play').click();
    await page.waitForFunction(() => window.__streetSceneCapture.snapshot().seconds > 0.05);
    await page.locator('#inspect').click();
    const inspected = await page.evaluate(() => window.__streetSceneCapture.snapshot());
    assert.equal(inspected.mode, 'inspection');
    assert.equal(inspected.transport, 'paused');
    assert.equal(await page.locator('#play').isDisabled(), true);
    assert.equal(await page.locator('#restart').isDisabled(), true);
    await page.keyboard.press('Escape');
    const restored = await page.evaluate(() => window.__streetSceneCapture.snapshot());
    assert.equal(restored.mode, 'authored');
    assert.equal(restored.transport, 'paused');
    assert.equal(restored.seconds, inspected.seconds);
    await page.evaluate(() => window.__streetSceneCapture.seek(5));
    await page.locator('#inspect').click();
    await page.locator('#inspect').click();
    assert.equal(await page.evaluate(() => window.__streetSceneCapture.snapshot().transport), 'ended');
    await page.locator('#restart').click();
    await page.waitForFunction(() => window.__streetSceneCapture.snapshot().transport === 'playing');
    await page.locator('#play').click();
    const paused = await page.evaluate(() => window.__streetSceneCapture.snapshot());
    assert.equal(paused.transport, 'paused');
    assert.ok(paused.seconds < 5);
    for (const name of Object.keys(anchor.wheelRotations)) {
      assert.ok(sampled.wheelRotations[name].every((value, index) =>
        Math.abs(value - anchor.wheelRotations[name][index]) < 1e-6));
    }
  }
  const gpu = await page.evaluate(() => {
    const gl = document.querySelector('canvas').getContext('webgl2');
    const extension = gl.getExtension('WEBGL_debug_renderer_info');
    return extension ? gl.getParameter(extension.UNMASKED_RENDERER_WEBGL) : 'unavailable';
  });
  for (const route of ['/interactive/', '/assets/']) {
    const response = await page.request.get(`${origin}${route}`);
    assert.equal(response.status(), 404);
  }
  await writeFile(path.join(output, 'proof.json'),
    JSON.stringify({ complete: errors.length === 0, coldStartupMs, gpu,
      browser: browser.version(), captures, errors }, null, 2));
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ coldStartupMs, gpu, captures: captures.map(({ frame, mainDrawCalls, shadowDrawCalls }) =>
    ({ frame, mainDrawCalls, shadowDrawCalls })) }));
} finally {
  await browser.close();
}
