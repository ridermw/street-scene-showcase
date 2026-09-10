import assert from 'node:assert/strict';
import test from 'node:test';
import { fitViewport } from '../../web/viewer.js';

test('fits an uncropped 16:9 rectangle and caps real device pixel ratio', () => {
  assert.deepEqual(fitViewport(1280, 720, 2, false), { width: 1280, height: 720, dpr: 1.5 });
  assert.deepEqual(fitViewport(390, 844, 3, false), { width: 390, height: 219.375, dpr: 1 });
  assert.equal(fitViewport(844, 390, 2, true).dpr, 1);
  assert.equal(fitViewport(1920, 1080, 1, false).dpr, 1);
  assert.equal(fitViewport(0, 100, 1, false), null);
});
