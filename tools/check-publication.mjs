import { createHash } from 'node:crypto';
import { lstat, readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';
import { NodeIO, VertexLayout } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { MeshoptDecoder, MeshoptEncoder } from 'meshoptimizer';
import validator from 'gltf-validator';
import { Matrix4, PerspectiveCamera, Vector3 } from 'three';
import { validateManifest } from '../web/contract.js';
import { inspectGlb } from '../web/scene.js';

await MeshoptDecoder.ready;

export const SOURCE_SHA256 = '0e4c90b1ab5bcfb052d2f5d2c5c4628a89b5b7145f6b6e9bf399d7f31cda4d05';
export const VIDEO_SHA256 = '31b4c10b7051ce67b980fbc12d39b5eedf1bbcf37ec168be1cc8f6c270dd1b1e';
export const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const requireValue = (condition, message) => { if (!condition) throw new Error(message); };

export function createIO({ preserveIndexOrder = false } = {}) {
  const encoder = preserveIndexOrder ? {
    ...MeshoptEncoder,
    encodeGltfBuffer: (source, count, size, mode) => mode === 'ATTRIBUTES'
      ? MeshoptEncoder.encodeVertexBufferLevel(source, count, size, 3, 0)
      : MeshoptEncoder.encodeGltfBuffer(source, count, size, mode === 'TRIANGLES' ? 'INDICES' : mode),
  } : MeshoptEncoder;
  return new NodeIO().setAllowNetwork(false).registerExtensions(ALL_EXTENSIONS)
    .setVertexLayout(VertexLayout.SEPARATE)
    .registerDependencies({ 'meshopt.decoder': MeshoptDecoder, 'meshopt.encoder': encoder });
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') {
    requireValue(Object.getPrototypeOf(value) === Object.prototype, 'Review settings must contain plain JSON records');
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
  }
  if (typeof value === 'number' && !Number.isFinite(value)) throw new Error('Nonfinite review setting');
  requireValue(value === null || ['string', 'number', 'boolean'].includes(typeof value), 'Invalid review setting');
  return value;
}

export function scanPublicText(text) {
  const normalized = text.replaceAll('\\', '/');
  requireValue(!/\/Users\/|\/home\/|\/private\/|\/var\/folders\/|file:\/\/|run-\d{8}T|street-scene-1-data|construction_fingerprint|retained_dependencies/i
    .test(normalized), 'Private source metadata in public content');
}

export async function walkFiles(root, relative = '') {
  const info = await lstat(path.join(root, relative));
  requireValue(!info.isSymbolicLink(), 'Symlinks are not permitted in curated public inputs');
  if (info.isFile()) return [relative.replaceAll(path.sep, '/')];
  requireValue(info.isDirectory(), 'Unsupported public file type');
  const files = [];
  for (const name of (await readdir(path.join(root, relative))).sort()) {
    files.push(...await walkFiles(root, path.join(relative, name)));
  }
  return files;
}

function arraySignature(accessor) {
  if (!accessor) return null;
  const array = accessor.getArray();
  requireValue(array && Array.from(array).every(Number.isFinite), 'Invalid decoded accessor');
  return {
    type: accessor.getType(), componentType: accessor.getComponentType(), normalized: accessor.getNormalized(),
    bytes: hash(Buffer.from(array.buffer, array.byteOffset, array.byteLength)),
  };
}

function textureSignature(texture, info) {
  if (!texture) return null;
  requireValue(texture.getImage(), 'Missing embedded texture');
  const transform = info?.getExtension('KHR_texture_transform');
  return {
    image: hash(texture.getImage()), mime: texture.getMimeType(), size: texture.getSize(),
    texCoord: info?.getTexCoord(), wrapS: info?.getWrapS(), wrapT: info?.getWrapT(),
    min: info?.getMinFilter(), mag: info?.getMagFilter(),
    transform: transform ? [transform.getOffset(), transform.getRotation(), transform.getScale()] : null,
  };
}

function materialSignature(material) {
  const coat = material.getExtension('KHR_materials_clearcoat');
  const emissive = material.getExtension('KHR_materials_emissive_strength');
  return {
    base: material.getBaseColorFactor(), metallic: material.getMetallicFactor(),
    roughness: material.getRoughnessFactor(), emissive: material.getEmissiveFactor(),
    emissionStrength: emissive?.getEmissiveStrength() ?? 1,
    alpha: material.getAlphaMode(), cutoff: material.getAlphaCutoff(), doubleSided: material.getDoubleSided(),
    normalScale: material.getNormalScale(), occlusionStrength: material.getOcclusionStrength(),
    textures: ['BaseColor', 'MetallicRoughness', 'Normal', 'Occlusion', 'Emissive'].map(name =>
      textureSignature(material[`get${name}Texture`](), material[`get${name}TextureInfo`]())),
    coat: coat ? {
      factor: coat.getClearcoatFactor(), roughness: coat.getClearcoatRoughnessFactor(),
      normalScale: coat.getClearcoatNormalScale(),
      textures: ['Clearcoat', 'ClearcoatRoughness', 'ClearcoatNormal'].map(name =>
        textureSignature(coat[`get${name}Texture`](), coat[`get${name}TextureInfo`]())),
    } : null,
  };
}

export function documentSnapshot(document) {
  const root = document.getRoot();
  const nodes = root.listNodes().map(node => {
    const camera = node.getCamera();
    const light = node.getExtension('KHR_lights_punctual');
    return {
      name: node.getName(), children: node.listChildren().map(child => child.getName()).sort(),
      translation: node.getTranslation(), rotation: node.getRotation(), scale: node.getScale(),
      camera: camera ? [camera.getType(), camera.getYFov(), camera.getAspectRatio(), camera.getZNear(), camera.getZFar()] : null,
      light: light ? [light.getType(), light.getColor(), light.getIntensity()] : null,
      primitives: node.getMesh()?.listPrimitives().map(primitive => ({
        mode: primitive.getMode(), indices: arraySignature(primitive.getIndices()),
        attributes: Object.fromEntries(primitive.listSemantics().sort()
          .map(semantic => [semantic, arraySignature(primitive.getAttribute(semantic))])),
        material: materialSignature(primitive.getMaterial()),
      })) ?? null,
    };
  }).sort((a, b) => a.name.localeCompare(b.name, 'en'));
  const animations = root.listAnimations().map(clip => ({
    name: clip.getName(),
    channels: clip.listChannels().map(channel => ({
      node: channel.getTargetNode().getName(), path: channel.getTargetPath(),
      interpolation: channel.getSampler().getInterpolation(),
      input: arraySignature(channel.getSampler().getInput()),
      output: arraySignature(channel.getSampler().getOutput()),
    })).sort((a, b) => `${a.node}.${a.path}`.localeCompare(`${b.node}.${b.path}`, 'en')),
  }));
  return canonical({ nodes, animations,
    scenes: root.listScenes().map(scene => ({ name: scene.getName(), children: scene.listChildren().map(n => n.getName()).sort() })),
    defaultScene: root.getDefaultScene()?.getName() ?? null,
  });
}

export function documentSignature(document) {
  return hash(JSON.stringify(documentSnapshot(document)));
}

export function inspectDocument(document, manifest) {
  const root = document.getRoot();
  const nodes = root.listNodes();
  requireValue(root.listScenes().length === 1, 'Expected one reachable scene');
  const reachable = new Set();
  function visit(node) {
    requireValue(!reachable.has(node), 'Scene node is reachable more than once');
    reachable.add(node);
    node.listChildren().forEach(visit);
  }
  root.listScenes()[0].listChildren().forEach(visit);
  requireValue(reachable.size === nodes.length, 'All logical nodes must be reachable from the scene');
  const names = new Map();
  for (const node of nodes) {
    requireValue(!names.has(node.getName()), 'Duplicate node name');
    names.set(node.getName(), node);
    requireValue(node.getWorldMatrix().every(Number.isFinite), 'Nonfinite transform');
  }
  const roleNames = [manifest.roles.camera, manifest.roles.hero, manifest.roles.sun, ...Object.values(manifest.roles.wheels)];
  requireValue(roleNames.every(name => names.has(name)), 'Missing required role');
  const camera = names.get(manifest.roles.camera).getCamera();
  const expected = manifest.expected.camera;
  requireValue(camera && camera.getType() === 'perspective'
    && Math.abs(camera.getYFov() - expected.yfov) < 1e-5
    && Math.abs(camera.getAspectRatio() - expected.aspect) < 1e-5
    && Math.abs(camera.getZNear() - expected.near) < 1e-5
    && Math.abs(camera.getZFar() - expected.far) < 1e-5, 'Camera projection mismatch');
  const projection = new PerspectiveCamera(camera.getYFov() * 180 / Math.PI,
    camera.getAspectRatio(), camera.getZNear(), camera.getZFar()).projectionMatrix.elements;
  requireValue(projection.every((value, i) => Math.abs(value - expected.projection[i]) < 1e-5),
    'Camera projection assertion mismatch');
  const sun = names.get(manifest.roles.sun);
  requireValue(sun.getExtension('KHR_lights_punctual')?.getType() === 'directional', 'Missing directional sun');
  const direction = new Vector3(0, 0, -1).transformDirection(new Matrix4().fromArray(sun.getWorldMatrix()));
  requireValue(direction.distanceTo(new Vector3(...manifest.lighting.sunDirection)) < 1e-5, 'Sun direction mismatch');
  const clips = root.listAnimations();
  requireValue(clips.length === 1 && clips[0].getName() === manifest.animation.clip, 'Missing or duplicate animation');
  const channels = clips[0].listChannels();
  const targets = new Set(channels.map(channel => channel.getTargetNode()?.getName()));
  requireValue(channels.length === 6 && targets.size === 6
    && roleNames.filter(name => name !== manifest.roles.sun).every(name => targets.has(name)),
  'Animation must contain all six source controls exactly once');
  for (const channel of channels) {
    const sampler = channel.getSampler();
    const times = sampler.getInput()?.getArray();
    requireValue(times?.length === 120 && times.every((time, i) => Math.abs(time - i / 24) < 1e-6),
      'Source sample times changed');
    requireValue(sampler.getInterpolation() === 'LINEAR', 'Unexpected source interpolation');
    const values = sampler.getOutput()?.getArray();
    requireValue(values && values.every(Number.isFinite), 'Nonfinite motion track');
    if (Object.values(manifest.roles.wheels).includes(channel.getTargetNode().getName())) {
      requireValue(channel.getTargetPath() === 'rotation' && values.length === 480, 'Missing wheel rotation samples');
      let total = 0;
      for (let i = 0; i < 120; i++) {
        const [x, y, z, w] = values.slice(i * 4, i * 4 + 4);
        requireValue(Math.abs(y) < 1e-6 && Math.abs(z) < 1e-6
          && Math.abs(Math.hypot(x, y, z, w) - 1) < 1e-5, 'Invalid wheel rotation');
        if (i) {
          const px = values[(i - 1) * 4], pw = values[(i - 1) * 4 + 3];
          let dx = pw * x - px * w, dw = pw * w + px * x;
          if (dw < 0) { dx = -dx; dw = -dw; }
          const delta = 2 * Math.atan2(dx, dw);
          requireValue(Math.abs(delta - manifest.expected.wheelRadians / 119) < 1e-4, 'Broken signed wheel continuity');
          total += delta;
        }
      }
      requireValue(Math.abs(total - manifest.expected.wheelRadians) < 1e-4, 'Broken signed wheel continuity');
    } else {
      requireValue(channel.getTargetPath() === 'translation' && values.length === 360, 'Missing translation samples');
      requireValue(Math.abs(values[values.length - 1] - values[2] + 17.5) < 1e-4, 'Authored travel changed');
    }
  }
  let triangleCount = 0, mainPassCeiling = 0, logicalObjects = 0;
  for (const node of nodes) {
    if (!node.getMesh()) continue;
    logicalObjects++;
    for (const primitive of node.getMesh().listPrimitives()) {
      requireValue(primitive.getMode() === 4 && primitive.getIndices(), 'Unsupported primitive geometry');
      requireValue(primitive.getAttribute('POSITION') && primitive.getAttribute('NORMAL'), 'Missing geometry attributes');
      triangleCount += primitive.getIndices().getCount() / 3;
      mainPassCeiling++;
    }
  }
  const buffers = new Set();
  let decodedGeometryBytes = 0;
  for (const accessor of root.listAccessors()) {
    const array = accessor.getArray();
    requireValue(array && array.every(Number.isFinite), 'Invalid decoded accessor');
    if (!buffers.has(array)) { buffers.add(array); decodedGeometryBytes += array.byteLength; }
  }
  let estimatedTextureBytes = 0;
  for (const texture of root.listTextures()) {
    const size = texture.getSize();
    requireValue(size && size.every(value => value >= 1 && value <= 4096), 'Missing or unbounded texture');
    scanPublicText(Buffer.from(texture.getImage()).toString('utf8'));
    estimatedTextureBytes += Math.ceil(size[0] * size[1] * 4 * 4 / 3);
  }
  return {
    triangleCount, mainPassCeiling, logicalObjects, materialCount: root.listMaterials().length,
    imageCount: root.listTextures().length, decodedGeometryBytes, estimatedTextureBytes,
  };
}

export async function decodeAsset(bytes) {
  const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  const json = inspectGlb(buffer);
  scanPublicText(JSON.stringify(json));
  const document = await createIO().readBinary(new Uint8Array(bytes));
  return { document, json };
}

function inspectImageMetadata(texture) {
  const bytes = Buffer.from(texture.getImage());
  scanPublicText(bytes.toString('utf8').replaceAll('\0', ''));
  if (texture.getMimeType() !== 'image/png') return;
  const allowed = new Set(['IHDR', 'IDAT', 'IEND', 'PLTE', 'tRNS', 'sRGB', 'gAMA', 'cHRM']);
  let offset = 8;
  while (offset < bytes.length) {
    requireValue(offset + 12 <= bytes.length, 'Truncated PNG metadata');
    const length = bytes.readUInt32BE(offset);
    const kind = bytes.subarray(offset + 4, offset + 8).toString('ascii');
    requireValue(offset + 12 + length <= bytes.length && allowed.has(kind), 'Unreviewed image metadata');
    offset += 12 + length;
  }
}

/** @returns {Promise<import('../web/contract.js').AssetReport>} */
export async function validateWebAsset(directory) {
  const files = await walkFiles(directory);
  const manifestBytes = await readFile(path.join(directory, 'scene-manifest.json'));
  scanPublicText(manifestBytes.toString());
  const manifest = validateManifest(JSON.parse(manifestBytes));
  requireValue(manifest.sourceSceneSha256 === SOURCE_SHA256, 'Wrong frozen source identity');
  const expectedFiles = [manifest.asset.file, 'scene-manifest.json', 'THIRD_PARTY_NOTICES.txt'].sort();
  requireValue(JSON.stringify(files.sort()) === JSON.stringify(expectedFiles), 'Unexpected or incomplete scene package');
  const bytes = await readFile(path.join(directory, manifest.asset.file));
  requireValue(bytes.length === manifest.asset.bytes && hash(bytes) === manifest.asset.sha256, 'Cached model or asset hash mismatch');
  const notices = await readFile(path.join(directory, 'THIRD_PARTY_NOTICES.txt'));
  scanPublicText(notices.toString());
  requireValue(notices.includes('Three.js') && notices.includes('meshoptimizer') && notices.includes('MIT License'),
    'Runtime license notices are incomplete');
  const assetBytes = bytes.length + manifestBytes.length + notices.length;
  requireValue(assetBytes <= manifest.limits.sceneBytes, 'Scene package exceeds the 30 MiB budget');
  for (const file of ['three/LICENSE', 'meshoptimizer/LICENSE.md']) {
    requireValue(notices.includes(await readFile(new URL(`../node_modules/${file}`, import.meta.url))),
      'Runtime license notices are incomplete');
  }
  const { document } = await decodeAsset(bytes);
  document.getRoot().listTextures().forEach(inspectImageMetadata);
  const statistics = inspectDocument(document, manifest);
  requireValue(statistics.triangleCount <= manifest.limits.triangles, 'Exported triangle budget exceeded');
  requireValue(statistics.mainPassCeiling <= manifest.limits.drawCalls, 'Main-pass draw-call budget exceeded');
  for (const [actual, expected] of [
    [statistics.triangleCount, manifest.statistics.triangles],
    [statistics.materialCount, manifest.statistics.materials],
    [statistics.imageCount, manifest.statistics.images],
    [statistics.logicalObjects, manifest.statistics.logicalObjects],
    [statistics.decodedGeometryBytes, manifest.statistics.geometryBytes],
    [document.getRoot().listTextures().reduce((total, texture) => total + texture.getImage().byteLength, 0),
      manifest.statistics.textureBytes],
  ]) requireValue(actual === expected, 'Decoded inventory differs from manifest');
  for (const material of manifest.materials) {
    for (const expected of material.generatedTextures) {
      const matches = document.getRoot().listTextures().filter(texture => texture.getName() === expected.name);
      requireValue(matches.length === 1 && hash(matches[0].getImage()) === expected.sha256
        && matches[0].getSize()[0] === expected.width && matches[0].getSize()[1] === expected.height,
      'Generated texture provenance mismatch');
    }
  }
  const result = await validator.validateBytes(new Uint8Array(bytes), { maxIssues: 1000 });
  const unsupported = result.issues.messages.filter(issue => issue.code === 'UNSUPPORTED_EXTENSION');
  requireValue(unsupported.every(issue => issue.message.includes("'EXT_meshopt_compression'")),
    'Unclassified unsupported extension diagnostic');
  const errors = result.issues.messages.filter(issue => issue.severity === 0 && issue.code !== 'UNSUPPORTED_EXTENSION');
  requireValue(errors.length === 0, `Khronos validation failed: ${JSON.stringify(errors.slice(0, 5))}`);
  const warnings = result.issues.messages.filter(issue => issue.severity <= 1 && issue.code !== 'UNSUPPORTED_EXTENSION');
  requireValue(warnings.length === 0, `Unclassified Khronos warnings: ${JSON.stringify(warnings.slice(0, 5))}`);
  return {
    glbSha256: manifest.asset.sha256, assetBytes, ...statistics, bundleGzipBytes: 0,
    warnings: unsupported.map(issue => `Validator cannot inspect ${issue.message}; decoded invariants checked independently.`),
  };
}

export async function computeReviewIdentity({ site, settings, sourceSceneSha256, sourceFrameHashes }) {
  requireValue(settings && typeof settings === 'object' && !Array.isArray(settings)
    && Object.keys(settings).length > 0, 'Review settings are required');
  requireValue(/^[a-f0-9]{64}$/.test(sourceSceneSha256), 'Review source hash missing');
  requireValue(sourceFrameHashes?.length === 3 && sourceFrameHashes.every(value => /^[a-f0-9]{64}$/.test(value)),
    'Three source-frame hashes are required');
  const files = {};
  for (const file of await walkFiles(site)) files[file] = hash(await readFile(path.join(site, file)));
  return hash(JSON.stringify(canonical({ files, settings, sourceSceneSha256, sourceFrameHashes })));
}

export const historicalFiles = [
  '.nojekyll', 'index.html', 'concept.html', 'attempts.html', 'attempts.json', 'style.css',
  'assets/final.jpg', 'assets/street-scene-attempt-23.mp4',
  ...Array.from({ length: 23 }, (_, i) => i + 1).filter(n => n !== 4)
    .map(n => `assets/attempt-${String(n).padStart(2, '0')}.jpg`),
];

export async function checkPublication(site) {
  const report = await validateWebAsset(path.join(site, 'assets/interactive'));
  const manifest = JSON.parse(await readFile(path.join(site, 'assets/interactive/scene-manifest.json')));
  const allowed = new Set([...historicalFiles, 'interactive/index.html',
    'assets/interactive/scene-manifest.json', 'assets/interactive/THIRD_PARTY_NOTICES.txt',
    `assets/interactive/${manifest.asset.file}`]);
  let bundleGzipBytes = 0, scriptCount = 0, cssCount = 0;
  for (const file of await walkFiles(site)) {
    const bytes = await readFile(path.join(site, file));
    if (/^interactive\/assets\/[A-Za-z0-9_-]+\.js$/.test(file)) {
      bundleGzipBytes += gzipSync(bytes, { level: 9 }).length;
      scriptCount++;
      scanPublicText(bytes.toString());
    } else if (/^interactive\/assets\/[A-Za-z0-9_-]+\.css$/.test(file)) {
      cssCount++;
      scanPublicText(bytes.toString());
    } else {
      requireValue(allowed.has(file), `Unexpected public file: ${file}`);
      if (/\.(html|json|txt|css)$/.test(file)) scanPublicText(bytes.toString());
    }
  }
  for (const file of allowed) await lstat(path.join(site, file));
  requireValue(scriptCount > 0 && cssCount > 0, 'Viewer bundle is missing');
  requireValue(bundleGzipBytes <= manifest.limits.bundleGzipBytes, 'Combined JavaScript gzip budget exceeded');
  requireValue(hash(await readFile(path.join(site, 'assets/street-scene-attempt-23.mp4'))) === VIDEO_SHA256,
    'Published video was changed');
  return { ...report, bundleGzipBytes };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const index = process.argv.indexOf('--site');
  if (index < 0 || !process.argv[index + 1]) throw new Error('Usage: npm run check -- --site <candidate-site>');
  console.log(JSON.stringify(await checkPublication(path.resolve(process.argv[index + 1])), null, 2));
}
