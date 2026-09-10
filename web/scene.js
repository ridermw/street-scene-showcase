import { AnimationClip, AnimationMixer, LoopOnce } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { validateManifest } from './contract.js';

const extensions = new Set([
  'KHR_lights_punctual', 'KHR_materials_clearcoat', 'KHR_materials_emissive_strength',
  'KHR_texture_transform', 'EXT_meshopt_compression',
]);

export function inspectGlb(buffer) {
  if (!(buffer instanceof ArrayBuffer) || buffer.byteLength < 28) throw new Error('Truncated GLB');
  const view = new DataView(buffer);
  if (view.getUint32(0, true) !== 0x46546c67 || view.getUint32(4, true) !== 2
    || view.getUint32(8, true) !== buffer.byteLength
    || view.getUint32(16, true) !== 0x4e4f534a) throw new Error('Invalid GLB header');
  const size = view.getUint32(12, true);
  if (size % 4 || 20 + size > buffer.byteLength) throw new Error('Invalid GLB JSON length');
  const json = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, 20, size)));
  if (json.asset?.version !== '2.0') throw new Error('Unsupported glTF version');
  for (const extension of json.extensionsRequired ?? []) {
    if (!extensions.has(extension)) throw new Error(`Unsupported required extension: ${extension}`);
  }
  function visit(value) {
    if (value === null || typeof value !== 'object') return;
    for (const [key, child] of Object.entries(value)) {
      if (key === 'uri' || key === 'extras') throw new Error('External resource or extras in GLB');
      visit(child);
    }
  }
  visit(json);
  for (const image of json.images ?? []) {
    if (!Number.isInteger(image.bufferView) || !['image/png', 'image/jpeg'].includes(image.mimeType)) {
      throw new Error('Missing or unsupported embedded image');
    }
  }
  return json;
}

export function disposeScene(root) {
  const geometries = new Set();
  const materials = new Set();
  const textures = new Set();
  root.traverse(node => {
    if (node.geometry) geometries.add(node.geometry);
    if (node.material) {
      for (const material of Array.isArray(node.material) ? node.material : [node.material]) {
        materials.add(material);
        for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
      }
    }
  });
  for (const geometry of geometries) geometry.dispose();
  for (const material of materials) material.dispose();
  const images = new Set();
  for (const texture of textures) {
    texture.dispose();
    if (texture.source?.data) images.add(texture.source.data);
  }
  for (const image of images) image.close?.();
}

/**
 * @typedef {{root:import('three').Object3D, camera:import('three').PerspectiveCamera,
 * roles:object, manifest:import('./contract.js').SceneManifest,
 * samplePose:(seconds:number)=>void, dispose:()=>void}} LoadedSceneBundle
 */

/** @returns {LoadedSceneBundle} */
export function createSceneBundle(gltf, manifest) {
  validateManifest(manifest);
  const root = gltf.scene;
  function role(name) {
    const matches = [];
    root.traverse(node => { if (node.name === name) matches.push(node); });
    if (matches.length !== 1) throw new Error(`Expected exactly one role: ${name}`);
    return matches[0];
  }
  const camera = role(manifest.roles.camera);
  const roles = {
    camera, hero: role(manifest.roles.hero), sun: role(manifest.roles.sun),
    wheels: Object.fromEntries(Object.entries(manifest.roles.wheels).map(([key, name]) => [key, role(name)])),
  };
  if (!camera.isPerspectiveCamera || !roles.sun.isDirectionalLight) {
    throw new Error('Camera or sun role has the wrong type');
  }
  const expected = manifest.expected.camera;
  if (Math.abs(camera.aspect - expected.aspect) > 1e-5
    || camera.projectionMatrix.elements.some((value, index) =>
      Math.abs(value - expected.projection[index]) > 1e-5)) {
    throw new Error('Authored camera projection differs from the source assertion');
  }
  root.traverse(node => {
    if ([...node.position, ...node.quaternion, ...node.scale].some(value => !Number.isFinite(value))) {
      throw new Error('Nonfinite scene transform');
    }
  });
  if (gltf.animations.length !== 1 || gltf.animations[0].name !== manifest.animation.clip) {
    throw new Error('Expected the single named source animation');
  }
  const sourceClip = gltf.animations[0];
  const clip = new AnimationClip(sourceClip.name, manifest.animation.durationSeconds, sourceClip.tracks);
  const mixer = new AnimationMixer(root);
  const action = mixer.clipAction(clip);
  action.setLoop(LoopOnce, 1);
  action.clampWhenFinished = true;
  let disposed = false;
  const bundle = {
    root, camera, roles, manifest,
    samplePose(seconds) {
      if (disposed) throw new Error('Scene is disposed');
      if (!Number.isFinite(seconds) || seconds < 0 || seconds > manifest.animation.durationSeconds) {
        throw new Error('Invalid scene sample time');
      }
      action.reset().play();
      mixer.setTime(seconds);
      root.updateMatrixWorld(true);
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      mixer.stopAllAction();
      mixer.uncacheRoot(root);
      disposeScene(root);
    },
  };
  bundle.samplePose(0);
  return bundle;
}

async function boundedBody(response, maximum, signal) {
  if (!response.ok) throw new Error(`Scene request failed (${response.status})`);
  const reader = response.body.getReader();
  const chunks = [];
  let bytes = 0;
  try {
    while (true) {
      signal?.throwIfAborted();
      const { value, done } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > maximum) throw new Error('Scene response exceeds its declared byte bound');
      chunks.push(value);
    }
  } catch (error) {
    await reader.cancel(error);
    throw error;
  } finally {
    reader.releaseLock();
  }
  const buffer = new Uint8Array(bytes);
  let offset = 0;
  for (const chunk of chunks) { buffer.set(chunk, offset); offset += chunk.byteLength; }
  return buffer.buffer;
}

export async function loadScene(manifestUrl, { signal } = {}) {
  const metrics = {};
  const started = performance.now();
  const manifestBody = await boundedBody(await fetch(manifestUrl, { signal }), 128 * 1024, signal);
  const manifest = validateManifest(JSON.parse(new TextDecoder().decode(manifestBody)));
  const url = new URL(manifest.asset.file, manifestUrl);
  const buffer = await boundedBody(await fetch(url, { signal }), manifest.asset.bytes, signal);
  if (buffer.byteLength !== manifest.asset.bytes) throw new Error('Scene byte count mismatch');
  const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', buffer))]
    .map(byte => byte.toString(16).padStart(2, '0')).join('');
  if (hash !== manifest.asset.sha256) throw new Error('Scene SHA256 mismatch');
  const json = inspectGlb(buffer);
  if (json.images?.length !== manifest.statistics.images) throw new Error('Embedded image inventory mismatch');
  metrics.fetchMs = performance.now() - started;
  const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
  const decodeStart = performance.now();
  const gltf = await loader.parseAsync(buffer, '');
  metrics.decodeMs = performance.now() - decodeStart;
  try {
    signal?.throwIfAborted();
    const bundle = createSceneBundle(gltf, manifest);
    return Object.assign(bundle, { metrics });
  } catch (error) {
    disposeScene(gltf.scene);
    throw error;
  }
}
