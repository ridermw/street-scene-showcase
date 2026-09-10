import { copyFile, mkdir, readFile, writeFile, lstat, mkdtemp } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { tmpdir } from 'node:os';
import { PropertyType } from '@gltf-transform/core';
import { EXTMeshoptCompression } from '@gltf-transform/extensions';
import { dedup } from '@gltf-transform/functions';
import { MeshoptEncoder } from 'meshoptimizer';
import { validateManifest } from '../web/contract.js';
import {
  checkPublication, computeReviewIdentity, createIO, decodeAsset, documentSignature,
  hash, historicalFiles, comparisonFiles, inspectDocument, validateWebAsset, walkFiles,
} from './check-publication.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

export async function optimizeImages(document) {
  const changes = [];
  for (const texture of document.getRoot().listTextures()) {
    if (texture.getMimeType() !== 'image/png') continue;
    const before = texture.getImage();
    const after = await new Promise((resolve, reject) => {
      const worker = spawn('python3', [path.join(ROOT, 'tools/optimize_png.py')], { stdio: ['pipe', 'pipe', 'pipe'] });
      const output = [], errors = [];
      worker.on('error', reject);
      worker.stdout.on('data', chunk => output.push(chunk));
      worker.stderr.on('data', chunk => errors.push(chunk));
      worker.stdin.on('error', reject);
      worker.on('close', code => code === 0 ? resolve(Buffer.concat(output))
        : reject(new Error(`PNG conversion failed: ${Buffer.concat(errors).toString()}`)));
      worker.stdin.end(before);
    });
    changes.push({ name: texture.getName(), before: hash(before), after: hash(after) });
    texture.setImage(new Uint8Array(after));
  }
  return changes;
}

export async function encodeLossless(document) {
  await MeshoptEncoder.ready;
  document.createExtension(EXTMeshoptCompression).setRequired(true).setEncoderOptions({
    method: EXTMeshoptCompression.EncoderMethod.QUANTIZE,
  });
  const encoded = Buffer.from(await createIO({ preserveIndexOrder: true }).writeBinary(document));
  const length = encoded.readUInt32LE(12);
  const json = JSON.parse(encoded.subarray(20, 20 + length));
  for (const view of json.bufferViews) {
    const compression = view.extensions?.EXT_meshopt_compression;
    if (compression?.mode === 'TRIANGLES') compression.mode = 'INDICES';
  }
  let text = Buffer.from(JSON.stringify(json));
  text = Buffer.concat([text, Buffer.alloc((4 - text.length % 4) % 4, 0x20)]);
  const binary = encoded.subarray(20 + length);
  const header = Buffer.alloc(20);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(20 + text.length + binary.length, 8);
  header.writeUInt32LE(text.length, 12);
  header.writeUInt32LE(0x4e4f534a, 16);
  return new Uint8Array(Buffer.concat([header, text, binary]));
}

export async function prepareWebAsset(input, manifest, outputDir) {
  const bytes = await readFile(input);
  const { document } = await decodeAsset(bytes);
  manifest = structuredClone(validateManifest(manifest));
  if (hash(bytes) !== manifest.asset.sha256 || bytes.length !== manifest.asset.bytes) {
    throw new Error('Raw baseline does not match its manifest');
  }
  inspectDocument(document, manifest);
  const baseline = documentSignature(document);
  await document.transform(dedup({
    keepUniqueNames: false,
    propertyTypes: [PropertyType.ACCESSOR, PropertyType.TEXTURE, PropertyType.MATERIAL, PropertyType.MESH],
  }));
  if (documentSignature(document) !== baseline) throw new Error('Deduplication changed source semantics');
  const counts = inspectDocument(document, manifest);
  if (counts.mainPassCeiling > manifest.limits.drawCalls) {
    throw new Error('Additional safe sibling batching is required before this candidate can proceed');
  }
  const imageChanges = await optimizeImages(document);
  for (const material of manifest.materials) {
    for (const texture of material.generatedTextures) {
      const change = imageChanges.find(item => item.name === texture.name);
      if (!change || texture.sha256 !== change.before) throw new Error('Generated image provenance mismatch');
      texture.sha256 = change.after;
    }
  }
  // Only embedded PNG bytes changed above, with exact decoded RGBA verified by the worker.
  const optimized = documentSignature(document);
  const encoded = await encodeLossless(document);
  const decoded = await createIO().readBinary(encoded);
  if (documentSignature(decoded) !== optimized) throw new Error('Compression changed decoded source data');
  const statistics = inspectDocument(decoded, manifest);
  const checksum = hash(encoded);
  manifest.asset = { file: `attempt-23.${checksum}.glb`, sha256: checksum, bytes: encoded.byteLength };
  Object.assign(manifest.statistics, {
    triangles: statistics.triangleCount, materials: statistics.materialCount,
    images: statistics.imageCount, logicalObjects: statistics.logicalObjects,
    geometryBytes: statistics.decodedGeometryBytes,
    textureBytes: decoded.getRoot().listTextures().reduce((total, texture) => total + texture.getImage().length, 0),
  });
  validateManifest(manifest);
  const notices = [
    'Three.js\n', await readFile(path.join(ROOT, 'node_modules/three/LICENSE'), 'utf8'),
    '\nmeshoptimizer\n', await readFile(path.join(ROOT, 'node_modules/meshoptimizer/LICENSE.md'), 'utf8'),
  ].join('\n');
  const json = JSON.stringify(manifest, null, 2) + '\n';
  if (encoded.byteLength + Buffer.byteLength(json + notices) > manifest.limits.sceneBytes) {
    throw new Error(`Lossless candidate exceeds the 30 MiB scene package budget: ${
      encoded.byteLength + Buffer.byteLength(json + notices)} bytes`);
  }
  await mkdir(outputDir, { recursive: false });
  await writeFile(path.join(outputDir, manifest.asset.file), encoded, { flag: 'wx' });
  await writeFile(path.join(outputDir, 'scene-manifest.json'), json, { flag: 'wx' });
  await writeFile(path.join(outputDir, 'THIRD_PARTY_NOTICES.txt'), notices, { flag: 'wx' });
  return validateWebAsset(outputDir);
}

export async function publishApprovedPackage(candidate, approval, destination, { copy = copyFile } = {}) {
  if (approval?.decision !== 'accept' || approval.authority !== 'user' || !approval.identity) {
    throw new Error('Explicit exact-candidate user approval is required');
  }
  // Validate every input and its approval before the first destination write.
  await checkPublication(candidate.site);
  const identity = await computeReviewIdentity(candidate);
  if (approval.identity !== identity) throw new Error('Visual approval is stale');
  const files = await walkFiles(candidate.site);
  const destinationRoot = path.resolve(destination);
  for (const file of files) {
    let parent = path.dirname(path.join(destinationRoot, file));
    while (parent.startsWith(destinationRoot)) {
      try {
        if ((await lstat(parent)).isSymbolicLink()) throw new Error('Publication destination contains a symlink');
      } catch (error) { if (error.code !== 'ENOENT') throw error; }
      if (parent === destinationRoot) break;
      parent = path.dirname(parent);
    }
    try {
      if ((await lstat(path.join(destinationRoot, file))).isSymbolicLink()) throw new Error('Publication file is a symlink');
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  // Copy is not a filesystem-wide transaction; any I/O failure blocks release integration.
  try {
    for (const file of files) {
      const target = path.join(destinationRoot, file);
      await mkdir(path.dirname(target), { recursive: true });
      await copy(path.join(candidate.site, file), target);
    }
  } catch (error) {
    throw new Error('Publication copy is incomplete; do not commit, push or merge this release', { cause: error });
  }
  await checkPublication(destinationRoot);
  if (await computeReviewIdentity({ ...candidate, site: destinationRoot }) !== identity) {
    throw new Error('Copied release differs from approved candidate');
  }
  return identity;
}

export async function preparePreview(site, outputRoot) {
  await checkPublication(site);
  const files = await walkFiles(site);
  const destination = path.join(outputRoot, 'street-scene-showcase');
  await mkdir(destination, { recursive: true });
  if ((await walkFiles(destination)).length) throw new Error('Preview destination must be empty');
  for (const file of files) {
    const target = path.join(destination, file);
    await mkdir(path.dirname(target), { recursive: true });
    await copyFile(path.join(site, file), target);
  }
  return destination;
}

export async function stageCandidate(assetDirectory, bundleDirectory, destination) {
  await validateWebAsset(assetDirectory);
  const sources = historicalFiles.map(file => [path.join(ROOT, 'docs', file), file]);
  if ((await walkFiles(path.join(ROOT, 'docs'))).includes('comparison.html')) {
    sources.push(...comparisonFiles.map(file => [path.join(ROOT, 'docs', file), file]));
  }
  sources.push([path.join(ROOT, 'docs/interactive/index.html'), 'interactive/index.html']);
  for (const file of await walkFiles(assetDirectory)) sources.push([path.join(assetDirectory, file), `assets/interactive/${file}`]);
  for (const file of await walkFiles(bundleDirectory)) {
    if (!/^[A-Za-z0-9_-]+\.(js|css)$/.test(file)) throw new Error('Unexpected generated bundle file');
    sources.push([path.join(bundleDirectory, file), `interactive/assets/${file}`]);
  }
  for (const [source] of sources) if ((await lstat(source)).isSymbolicLink()) throw new Error('Symlink in curated inputs');
  await mkdir(destination, { recursive: false });
  for (const [source, file] of sources) {
    const target = path.join(destination, file);
    await mkdir(path.dirname(target), { recursive: true });
    await copyFile(source, target);
  }
  for (const file of ['index.html', 'concept.html', 'attempts.html']) {
    const target = path.join(destination, file);
    let html = await readFile(target, 'utf8');
    if (!html.includes('href="interactive/index.html"')) {
      if ((html.match(/<\/nav>/g) ?? []).length !== 1) throw new Error('Expected one historical navigation');
      html = html.replace('</nav>', '  <a href="interactive/index.html">Interactive scene</a>\n</nav>');
    }
    if (!html.includes('rel="icon"')) html = html.replace('</head>', '  <link rel="icon" href="assets/final.jpg" type="image/jpeg">\n</head>');
    await writeFile(target, html);
  }
  await checkPublication(destination);
  return destination;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const argument = name => {
    const i = process.argv.indexOf(name);
    if (i < 0 || !process.argv[i + 1]) throw new Error(`Missing ${name}`);
    return path.resolve(process.argv[i + 1]);
  };
  if (process.argv.includes('--preview')) {
    const root = await mkdtemp(path.join(tmpdir(), 'street-preview-'));
    await preparePreview(argument('--site'), root);
    const server = spawn('python3', ['-m', 'http.server', '4173', '--bind', '127.0.0.1', '--directory', root],
      { stdio: 'inherit' });
    for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.kill(signal));
    server.on('error', error => { console.error(error); process.exitCode = 1; });
    server.on('exit', code => { process.exitCode = code ?? 1; });
  } else {
    console.log(JSON.stringify(await prepareWebAsset(argument('--input'),
      JSON.parse(await readFile(argument('--manifest'))), argument('--output')), null, 2));
  }
}
