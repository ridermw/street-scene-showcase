import assert from 'node:assert/strict';
import test from 'node:test';
import { createPlayback } from '../../web/playback.js';

test('starts paused and plays exactly five seconds with a final-pose hold interval', () => {
  const clock = createPlayback({ durationSeconds: 5 });
  assert.deepEqual(clock.snapshot(), { state: 'paused', seconds: 0 });
  clock.play();
  clock.tick(1000);
  clock.tick(3500);
  assert.deepEqual(clock.snapshot(), { state: 'playing', seconds: 2.5 });
  clock.tick(1000 + 119 / 24 * 1000);
  assert.ok(Math.abs(clock.snapshot().seconds - 119 / 24) < 1e-12);
  assert.equal(clock.snapshot().state, 'playing');
  clock.tick(6000);
  assert.deepEqual(clock.snapshot(), { state: 'ended', seconds: 5 });
  clock.tick(7000);
  assert.deepEqual(clock.snapshot(), { state: 'ended', seconds: 5 });
});

test('completed time does not depend on frame partitioning', () => {
  for (const ticks of [[0, 2500], [0, 100, 200, 1900, 2500]]) {
    const clock = createPlayback({ durationSeconds: 5 });
    clock.play();
    ticks.forEach(t => clock.tick(t));
    assert.equal(clock.snapshot().seconds, 2.5);
  }
});

test('pause or hidden-tab suspension excludes elapsed wall time and requires explicit play', () => {
  const clock = createPlayback({ durationSeconds: 5 });
  clock.play();
  clock.tick(0);
  clock.tick(1000);
  clock.pause();
  clock.tick(60000);
  assert.deepEqual(clock.snapshot(), { state: 'paused', seconds: 1 });
  clock.play();
  clock.tick(60000);
  clock.tick(60500);
  assert.equal(clock.snapshot().seconds, 1.5);
});

test('restart immediately plays from zero, and play at end restarts', () => {
  const clock = createPlayback({ durationSeconds: 5 });
  clock.seek(5);
  clock.pause();
  assert.equal(clock.snapshot().state, 'ended');
  clock.play();
  assert.deepEqual(clock.snapshot(), { state: 'playing', seconds: 0 });
  clock.tick(0);
  clock.tick(2000);
  clock.restart();
  assert.deepEqual(clock.snapshot(), { state: 'playing', seconds: 0 });
  clock.tick(10000);
  assert.equal(clock.snapshot().seconds, 0);
});

test('backward seeks reset timestamp anchoring and preserve paused intent', () => {
  const clock = createPlayback({ durationSeconds: 5 });
  clock.seek(5);
  clock.seek(2.5);
  assert.deepEqual(clock.snapshot(), { state: 'paused', seconds: 2.5 });
  clock.play();
  clock.tick(1000);
  clock.seek(1);
  clock.tick(9000);
  assert.deepEqual(clock.snapshot(), { state: 'playing', seconds: 1 });
  clock.tick(9500);
  assert.equal(clock.snapshot().seconds, 1.5);
});

test('repeated play does not discard time already anchored', () => {
  const clock = createPlayback({ durationSeconds: 5 });
  clock.play();
  clock.tick(0);
  clock.play();
  clock.tick(1000);
  assert.equal(clock.snapshot().seconds, 1);
});

test('invalid duration, seeks and timestamps fail without changing state', () => {
  for (const durationSeconds of [0, -1, NaN, Infinity, '5']) assert.throws(() => createPlayback({ durationSeconds }));
  const clock = createPlayback({ durationSeconds: 5 });
  for (const seconds of [-1, 5.001, Infinity, NaN, '1', null]) assert.throws(() => clock.seek(seconds));
  assert.deepEqual(clock.snapshot(), { state: 'paused', seconds: 0 });
  clock.play();
  for (const time of [-1, NaN, Infinity, '0']) assert.throws(() => clock.tick(time));
  clock.tick(1000);
  assert.throws(() => clock.tick(999), /monotonic/);
  assert.equal(clock.snapshot().seconds, 0);
});
