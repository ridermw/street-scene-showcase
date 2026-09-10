import assert from 'node:assert/strict';
import test from 'node:test';
import { DirectionalLight, Group, PerspectiveCamera, Vector3 } from 'three';
import { fitViewport, createCameraRig, createTeardown } from '../../web/viewer.js';
import { createPlayback } from '../../web/playback.js';
import { configureShadowFrustum, environmentPixels } from '../../web/lighting.js';
import { manifestFixture } from './fixtures.mjs';

test('fits an uncropped 16:9 rectangle and caps real device pixel ratio', () => {
  assert.deepEqual(fitViewport(1280, 720, 2, false), { width: 1280, height: 720, dpr: 1.5 });
  assert.deepEqual(fitViewport(390, 844, 3, false), { width: 390, height: 219.375, dpr: 1 });
  assert.equal(fitViewport(844, 390, 2, true).dpr, 1);
  assert.equal(fitViewport(1920, 1080, 1, false).dpr, 1);
  assert.equal(fitViewport(0, 100, 1, false), null);
  for (const dpr of [0, -1, NaN, Infinity]) assert.throws(() => fitViewport(1280, 720, dpr, false));
  assert.equal(fitViewport(NaN, 100, 1, false), null);
});

test('inspection copies the world camera, pauses, and restores the unchanged authored camera', () => {
  const parent = new Group(), authored = new PerspectiveCamera(40, 16 / 9, 0.1, 800);
  parent.position.set(10, 0, 0);
  authored.position.set(1, 2, 3);
  parent.add(authored);
  parent.updateMatrixWorld(true);
  const clock = createPlayback({ durationSeconds: 5 });
  clock.play();
  clock.tick(0);
  clock.tick(1000);
  const rig = createCameraRig(authored, clock);
  rig.setInspection(true);
  assert.deepEqual(rig.camera.position.toArray(), [11, 2, 3]);
  assert.deepEqual(clock.snapshot(), { state: 'paused', seconds: 1 });
  rig.camera.position.x += 20;
  rig.setInspection(false);
  assert.equal(rig.camera, authored);
  assert.deepEqual(authored.position.toArray(), [1, 2, 3]);
  assert.deepEqual(clock.snapshot(), { state: 'paused', seconds: 1 });
  clock.seek(5);
  rig.setInspection(true);
  rig.setInspection(false);
  assert.deepEqual(clock.snapshot(), { state: 'ended', seconds: 5 });
});

test('teardown is ordered and idempotent, and one failing stage does not skip remaining releases', () => {
  const calls = [];
  const dispose = createTeardown([
    () => calls.push('stop'),
    () => { calls.push('listeners'); throw new Error('failure'); },
    () => calls.push('controls'),
    () => calls.push('lighting'),
    () => calls.push('scene'),
    () => calls.push('renderer'),
  ]);
  assert.throws(dispose, AggregateError);
  dispose();
  assert.deepEqual(calls, ['stop', 'listeners', 'controls', 'lighting', 'scene', 'renderer']);
});

test('fixed shadow coverage includes the whole travel without moving the authored sun', () => {
  const sun = new DirectionalLight();
  sun.rotation.x = -Math.PI / 4;
  sun.updateMatrixWorld(true);
  const before = sun.matrixWorld.toArray();
  const restore = configureShadowFrustum(sun, manifestFixture().lighting.shadow, new Vector3(0, 1, -10));
  sun.shadow.updateMatrices(sun);
  const matrix = sun.shadow.matrix.toArray();
  assert.equal(sun.shadow.getFrustum().containsPoint(new Vector3(0, 0, -2)), true);
  assert.equal(sun.shadow.getFrustum().containsPoint(new Vector3(0, 0, -19.5)), true);
  assert.deepEqual(sun.matrixWorld.toArray(), before);
  sun.shadow.updateMatrices(sun);
  assert.deepEqual(sun.shadow.matrix.toArray(), matrix);
  restore();
});

test('unflipped equirectangular data places the sky at positive-Y latitude', () => {
  const settings = manifestFixture().lighting;
  const { width, height, data } = environmentPixels(settings);
  for (let channel = 0; channel < 3; channel++) {
    assert.ok(Math.abs(data[channel] - settings.groundColor[channel]) < 1e-6);
    assert.ok(Math.abs(data[((height - 1) * width) * 4 + channel] - settings.skyColor[channel]) < 1e-6);
  }
  const street = ((Math.floor(height * 0.6) * width) + Math.floor(width / 4)) * 4;
  const wall = Math.floor(height * 0.6) * width * 4;
  assert.ok(data[street + 2] > data[wall + 2]);
});
