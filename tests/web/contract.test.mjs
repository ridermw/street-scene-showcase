import assert from 'node:assert/strict';
import test from 'node:test';
import { validateManifest } from '../../web/contract.js';
import { manifestFixture } from './fixtures.mjs';

test('accepts the allowlisted portable scene contract', () => {
  const input = manifestFixture();
  assert.deepEqual(validateManifest(input), input);
});

for (const path of [[], ['asset'], ['roles'], ['roles', 'wheels'], ['expected', 'camera'],
  ['lighting', 'shadow'], ['materials', 0], ['statistics'], ['limits']]) {
  test(`rejects unknown metadata at ${path.join('.') || 'root'}`, () => {
    const input = manifestFixture();
    let record = input;
    for (const key of path) record = record[key];
    record.privateSource = 'not public';
    assert.throws(() => validateManifest(input), /unknown/i);
  });
}

test('rejects wrong types, missing roles, schema drift and altered timing policy', () => {
  for (const mutate of [
    m => { m.schemaVersion = 2; }, m => { m.design = 'attempt-22'; },
    m => { m.asset.bytes = '1024'; }, m => { m.asset.bytes = NaN; },
    m => { m.expected.camera.yfov = Infinity; },
    m => { delete m.roles.wheels.rearRight; },
    m => { m.roles.camera = 'Camera'; }, m => { m.animation.motionEndSeconds = 5; },
    m => { m.animation.fps = 30; }, m => { m.limits.drawCalls = 1000; },
  ]) {
    const input = manifestFixture();
    mutate(input);
    assert.throws(() => validateManifest(input));
  }
});

test('rejects external, data, parent-traversal, mismatched and query-string GLB references', () => {
  for (const file of ['https://example.com/model.glb', 'data:model', '../model.glb',
    '/model.glb', 'attempt-23.raw.glb', `attempt-23.${'b'.repeat(64)}.glb`,
    `attempt-23.${'a'.repeat(64)}.glb?secret=1`]) {
    const input = manifestFixture();
    input.asset.file = file;
    assert.throws(() => validateManifest(input));
  }
});

test('rejects non-allowlisted provenance URLs and unsafe text', () => {
  for (const mutate of [
    m => { m.materials[0].sourceUrl = 'file:///source.jpg'; },
    m => { m.materials[0].licenseUrl = 'https://example.com/license'; },
    m => { m.materials[0].approximations = ['/Users/example/private']; },
    m => { m.materials[0].generatedTextures[0].name = '../image'; },
    m => { m.materials[0].inputHashes.color = 'not-a-hash'; },
  ]) {
    const input = manifestFixture();
    mutate(input);
    assert.throws(() => validateManifest(input));
  }
});
