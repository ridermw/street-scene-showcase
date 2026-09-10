import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp, readFile, writeFile, mkdir, cp, rm, symlink, lstat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { randomBytes } from 'node:crypto';
import { gzipSync } from 'node:zlib';
import { execFileSync } from 'node:child_process';
import { computeReviewIdentity, validateWebAsset, inspectDocument, decodeAsset, documentSignature,
  checkPublication } from '../../tools/check-publication.mjs';
import { prepareWebAsset, publishApprovedPackage, encodeLossless, optimizeImages, stageCandidate, preparePreview } from '../../tools/prepare-web-asset.mjs';
import { Document } from '@gltf-transform/core';
import { createIO } from '../../tools/check-publication.mjs';
import { assetFixture, mutateGlb, writeAssetFixture } from './asset-fixture.mjs';

test('image optimization fails explicitly on a malformed PNG', async () => {
  const document = new Document();
  document.createTexture('bad').setMimeType('image/png').setImage(new Uint8Array([1, 2, 3]));
  await assert.rejects(optimizeImages(document), /PNG conversion failed/);
});

test('lossless compression preserves original triangle index order, not only winding', async () => {
  const document = new Document();
  const buffer = document.createBuffer();
  const indices = document.createAccessor().setType('SCALAR').setBuffer(buffer)
    .setArray(new Uint16Array([2, 0, 1, 3, 2, 1]));
  const positions = document.createAccessor().setType('VEC3').setBuffer(buffer)
    .setArray(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 1, 0]));
  const primitive = document.createPrimitive().setIndices(indices).setAttribute('POSITION', positions);
  document.createScene().addChild(document.createNode().setMesh(document.createMesh().addPrimitive(primitive)));
  const decoded = await createIO().readBinary(await encodeLossless(document));
  assert.deepEqual([...decoded.getRoot().listMeshes()[0].listPrimitives()[0].getIndices().getArray()],
    [2, 0, 1, 3, 2, 1]);
});

test('rejects corrupt GLB before candidate output is created', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'street-asset-'));
  try {
    const input = path.join(root, 'bad.glb');
    await writeFile(input, 'not a GLB');
    await assert.rejects(prepareWebAsset(input, {}, path.join(root, 'candidate')), /GLB/);
    await assert.rejects(readFile(path.join(root, 'candidate', 'scene-manifest.json')), /ENOENT/);
  } finally { await rm(root, { recursive: true }); }
});

test('portable identity binds every logical file and canonical settings, not relocation', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'street-review-'));
  try {
    const site = path.join(root, 'site');
    await mkdir(site);
    for (const file of ['index.html', 'viewer.js', 'viewer.css', 'model.glb', 'manifest.json', 'notices.txt']) {
      await writeFile(path.join(site, file), `original ${file}`);
    }
    const input = { site, settings: { times: [0, 2.5, 119 / 24], width: 1920, dpr: 1 },
      sourceSceneSha256: 'a'.repeat(64), sourceFrameHashes: ['b'.repeat(64), 'c'.repeat(64), 'd'.repeat(64)] };
    const identity = await computeReviewIdentity(input);
    const moved = path.join(root, 'moved');
    await cp(site, moved, { recursive: true });
    assert.equal(await computeReviewIdentity({ ...input, site: moved }), identity);
    for (const file of ['index.html', 'viewer.js', 'viewer.css', 'model.glb', 'manifest.json', 'notices.txt']) {
      const original = await readFile(path.join(site, file));
      await writeFile(path.join(site, file), 'changed');
      assert.notEqual(await computeReviewIdentity(input), identity, file);
      await writeFile(path.join(site, file), original);
    }
    assert.notEqual(await computeReviewIdentity({ ...input, settings: { ...input.settings, dpr: 1.5 } }), identity);
    assert.notEqual(await computeReviewIdentity({ ...input, sourceFrameHashes: ['e'.repeat(64), ...input.sourceFrameHashes.slice(1)] }), identity);
    assert.notEqual(await computeReviewIdentity({ ...input, sourceSceneSha256: 'f'.repeat(64) }), identity);
    await assert.rejects(computeReviewIdentity({ ...input, settings: undefined }), /settings/i);
    await assert.rejects(computeReviewIdentity({ ...input, settings: { lighting: () => {} } }), /setting/i);
  } finally { await rm(root, { recursive: true }); }
});

test('publication refuses missing approval before touching the destination', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'street-publish-'));
  try {
    const destination = path.join(root, 'destination');
    await assert.rejects(publishApprovedPackage({ site: root }, null, destination), /approval/i);
    await assert.rejects(readFile(path.join(destination, 'index.html')), /ENOENT/);
  } finally { await rm(root, { recursive: true }); }
});

test('candidate validation rejects absent or incomplete packages', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'street-incomplete-'));
  try {
    await assert.rejects(validateWebAsset(root));
  } finally { await rm(root, { recursive: true }); }
});

test('complete small self-contained fixture passes decoded validation', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'street-valid-'));
  try {
    await writeAssetFixture(path.join(root, 'asset'));
    const report = await validateWebAsset(path.join(root, 'asset'));
    assert.equal(report.triangleCount, 1);
    assert.equal(report.logicalObjects, 1);
    assert.equal(report.imageCount, 1);
  } finally { await rm(root, { recursive: true }); }
});

for (const [name, mutate, error] of [
  ['missing role', f => f.nodes.WheelFL.setName('Missing'), /role/],
  ['duplicate role', f => f.scene.addChild(f.document.createNode('HeroCar')), /Duplicate/],
  ['wrong camera', f => f.nodes.ChaseCamera.getCamera().setYFov(1), /projection/],
  ['wrong clip', f => f.document.getRoot().listAnimations()[0].setName('Other'), /animation/],
  ['missing clip', f => f.document.getRoot().listAnimations()[0].dispose(), /animation/],
  ['duplicate clip', f => f.document.createAnimation('Other'), /animation/],
  ['nonfinite transform', f => f.geometry.setTranslation([NaN, 0, 0]), /Nonfinite/],
  ['wrong sample times', f => { f.document.getRoot().listAnimations()[0].listSamplers()[0].getInput().getArray()[50] += 0.01; }, /sample times/],
  ['missing wheel turns', f => f.document.getRoot().listAnimations()[0].listSamplers()[2].getOutput().getArray().fill(0), /wheel rotation/],
  ['out-and-back wheel discontinuity', f => {
    const values = f.document.getRoot().listAnimations()[0].listSamplers()[2].getOutput().getArray();
    values.set(values.slice(40, 44), 80);
  }, /continuity/],
  ['disconnected geometry', f => f.nodes.HeroCar.removeChild(f.geometry), /reachable/],
  ['wrong projection assertion', f => { f.manifest.expected.camera.projection[0] += 0.1; }, /projection/],
]) {
  test(`decoded validator rejects ${name}`, () => {
    const fixture = assetFixture();
    mutate(fixture);
    assert.throws(() => inspectDocument(fixture.document, fixture.manifest), error);
  });
}

for (const [name, mutate] of [
  ['external URI', j => { j.buffers[0].uri = 'https://invalid.example/model.bin'; }],
  ['data URI', j => { j.images[0].uri = 'data:image/png;base64,AAAA'; }],
  ['missing image', j => { delete j.images[0].bufferView; }],
  ['unknown required extension', j => { j.extensionsRequired = ['UNKNOWN_extension']; }],
  ['unknown optional extension', j => { j.extensionsUsed.push('UNKNOWN_extension'); }],
  ['private extras', j => { j.nodes[0].extras = { source: 'private' }; }],
  ['private path', j => { j.nodes[0].name = '/Users/example/source'; }],
  ['corrupt buffer', j => { j.buffers[0].byteLength = 2 ** 30; }],
]) {
  test(`raw validator rejects ${name}`, async () => {
    const bytes = await createIO().writeBinary(assetFixture().document);
    await assert.rejects(decodeAsset(mutateGlb(bytes, mutate)));
  });
}

test('semantic signature includes scene-root membership', () => {
  const f = assetFixture();
  const before = documentSignature(f.document);
  f.scene.removeChild(f.nodes.HeroCar);
  assert.notEqual(documentSignature(f.document), before);
});

test('rejects mismatched cached model, unsupported schema, false inventory and byte overruns', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'street-invalid-'));
  try {
    for (const [name, mutate] of [
      ['cached', m => { m.asset.bytes += 1; }],
      ['schema', m => { m.schemaVersion = 2; }],
      ['inventory', m => { m.statistics.triangles += 1; }],
      ['decoded bytes', m => { m.statistics.geometryBytes += 1; }],
      ['texture bytes', m => { m.statistics.textureBytes += 1; }],
      ['provenance', m => { m.materials[0].generatedTextures = [{ name: 'Absent', sha256: 'a'.repeat(64), width: 1, height: 1, usage: 'normal' }]; }],
    ]) {
      const directory = path.join(root, name);
      const fixture = await writeAssetFixture(directory);
      mutate(fixture.manifest);
      await writeFile(path.join(directory, 'scene-manifest.json'), JSON.stringify(fixture.manifest));
      await assert.rejects(validateWebAsset(directory), undefined, name);
    }
    const directory = path.join(root, 'large');
    await writeAssetFixture(directory);
    await writeFile(path.join(directory, 'THIRD_PARTY_NOTICES.txt'),
      'Three.js meshoptimizer MIT License\n' + 'x'.repeat(30 * 1024 ** 2));
    await assert.rejects(validateWebAsset(directory), /budget/);
  } finally { await rm(root, { recursive: true }); }
});

test('reaches actual triangle and draw-call budget checks', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'street-budgets-'));
  try {
    const triangles = assetFixture();
    triangles.primitive.getIndices().setArray(new Uint16Array(1100001 * 3));
    await writeAssetFixture(path.join(root, 'triangles'), triangles);
    await assert.rejects(validateWebAsset(path.join(root, 'triangles')), /triangle budget/);
    const calls = assetFixture();
    for (let i = 0; i < 300; i++) calls.scene.addChild(calls.document.createNode(`Extra${i}`).setMesh(calls.geometry.getMesh()));
    await writeAssetFixture(path.join(root, 'calls'), calls);
    await assert.rejects(validateWebAsset(path.join(root, 'calls')), /draw-call budget/);
  } finally { await rm(root, { recursive: true }); }
});

test('stale approval and copy failure cannot produce a successful publication', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'street-copy-'));
  try {
    const assets = path.join(root, 'asset'), bundle = path.join(root, 'bundle'), site = path.join(root, 'site');
    await writeAssetFixture(assets);
    await mkdir(bundle);
    await writeFile(path.join(bundle, 'viewer.js'), 'console.log("fixture")');
    await writeFile(path.join(bundle, 'viewer.css'), 'canvas{display:block}');
    await stageCandidate(assets, bundle, site);
    for (const file of ['index.html', 'concept.html', 'attempts.html']) {
      assert.match(await readFile(path.join(site, file), 'utf8'), /href="interactive\/index.html"/);
    }
    const candidate = { site, settings: { times: [0, 2.5, 119 / 24] },
      sourceSceneSha256: 'a'.repeat(64), sourceFrameHashes: ['b'.repeat(64), 'c'.repeat(64), 'd'.repeat(64)] };
    const identity = await computeReviewIdentity(candidate);
    const destination = path.join(root, 'published');
    await assert.rejects(publishApprovedPackage(candidate,
      { authority: 'user', decision: 'accept', identity: '0'.repeat(64) }, destination), /stale/);
    await assert.rejects(lstat(destination), /ENOENT/);
    let copied = 0;
    await assert.rejects(publishApprovedPackage(candidate,
      { authority: 'user', decision: 'accept', identity }, destination,
      { copy: async (source, target) => {
        if (copied++ === 2) throw new Error('Injected I/O failure');
        await cp(source, target);
      } }), /incomplete/);
    assert.equal((await lstat(path.join(destination, '.nojekyll'))).isFile(), true);
    const preview = path.join(root, 'preview');
    await preparePreview(site, preview);
    assert.equal(await computeReviewIdentity({ ...candidate, site: path.join(preview, 'street-scene-showcase') }), identity);
    await writeFile(path.join(site, 'private.txt'), 'unexpected');
    await assert.rejects(checkPublication(site), /Unexpected/);
    await rm(path.join(site, 'private.txt'));
    const chunk = Buffer.from(randomBytes(600000).toString('hex'));
    assert.ok(gzipSync(chunk).length < 1024 ** 2);
    await writeFile(path.join(site, 'interactive/assets/viewer.js'), chunk);
    await writeFile(path.join(site, 'interactive/assets/lazy.js'), chunk);
    await assert.rejects(checkPublication(site), /Combined JavaScript/);
    await rm(path.join(site, 'interactive/assets/lazy.js'));
    await writeFile(path.join(site, 'interactive/assets/viewer.js'), 'console.log("fixture")');
    const html = await readFile(path.join(site, 'interactive/index.html'), 'utf8');
    await writeFile(path.join(site, 'interactive/index.html'), html.replace('./assets/viewer.js', './assets/missing.js'));
    await assert.rejects(checkPublication(site), /ENOENT|link/);
    await writeFile(path.join(site, 'interactive/index.html'), html);
    await symlink(path.join(root, 'asset'), path.join(site, 'escape'));
    await assert.rejects(preparePreview(site, path.join(root, 'bad-preview')), /Symlink/);
  } finally { await rm(root, { recursive: true }); }
});

test('rejects compressed image metadata and incomplete license text', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'street-metadata-'));
  try {
    const fixture = assetFixture();
    const png = execFileSync('python3', ['-c',
      'from PIL import Image,PngImagePlugin; import sys; info=PngImagePlugin.PngInfo(); info.add_text("Comment","private source record",zip=True); Image.new("RGB",(1,1)).save(sys.stdout.buffer,format="PNG",pnginfo=info)']);
    fixture.texture.setImage(png);
    await writeAssetFixture(path.join(root, 'metadata'), fixture);
    await assert.rejects(validateWebAsset(path.join(root, 'metadata')), /metadata/);
    await writeAssetFixture(path.join(root, 'notices'));
    await writeFile(path.join(root, 'notices', 'THIRD_PARTY_NOTICES.txt'), 'Three.js meshoptimizer MIT License');
    await assert.rejects(validateWebAsset(path.join(root, 'notices')), /license/);
  } finally { await rm(root, { recursive: true }); }
});
