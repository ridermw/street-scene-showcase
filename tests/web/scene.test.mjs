import assert from 'node:assert/strict';
import test from 'node:test';
import {
  AnimationClip, DirectionalLight, Group, PerspectiveCamera,
  Quaternion, QuaternionKeyframeTrack, Vector3, VectorKeyframeTrack,
} from 'three';
import { createSceneBundle, inspectGlb } from '../../web/scene.js';
import { manifestFixture } from './fixtures.mjs';

function fixture() {
  const manifest = manifestFixture();
  const scene = new Group();
  const camera = new PerspectiveCamera(manifest.expected.camera.yfov * 180 / Math.PI, 16 / 9, 0.1, 800);
  camera.name = 'ChaseCamera';
  manifest.expected.camera.projection = [...camera.projectionMatrix.elements];
  scene.add(camera);
  const hero = new Group();
  hero.name = 'HeroCar';
  scene.add(hero);
  const sun = new DirectionalLight();
  sun.name = 'Sun';
  scene.add(sun);
  const times = Array.from({ length: 120 }, (_, i) => i / 24);
  const values = times.flatMap((_, i) => [0, 0, -17.5 * i / 119]);
  const tracks = [
    new VectorKeyframeTrack('HeroCar.position', times, values),
    new VectorKeyframeTrack('ChaseCamera.position', times, values),
  ];
  for (const name of Object.values(manifest.roles.wheels)) {
    const wheel = new Group();
    wheel.name = name;
    hero.add(wheel);
    const rotations = times.flatMap((_, i) =>
      new Quaternion().setFromAxisAngle(new Vector3(1, 0, 0), -17.5 / 0.36 * i / 119).toArray());
    tracks.push(new QuaternionKeyframeTrack(`${name}.quaternion`, times, rotations));
  }
  const animations = [new AnimationClip('StreetSequence', 119 / 24, tracks)];
  return { gltf: { scene, animations }, manifest };
}

test('samples the actual mixer backward after the five-second final hold', () => {
  const { gltf, manifest } = fixture();
  const bundle = createSceneBundle(gltf, manifest);
  bundle.samplePose(5);
  assert.ok(Math.abs(bundle.roles.hero.position.z + 17.5) < 1e-5);
  bundle.samplePose(2.5);
  assert.ok(Math.abs(bundle.roles.hero.position.z + 17.5 * 60 / 119) < 1e-5);
  bundle.samplePose(0);
  assert.ok(Math.abs(bundle.roles.hero.position.z) < 1e-7);
  assert.ok(bundle.roles.wheels.frontLeft.quaternion.angleTo(new Quaternion()) < 1e-5);
  bundle.dispose();
  bundle.dispose();
  assert.throws(() => bundle.samplePose(1), /disposed/);
});

test('rejects absent or duplicate roles, wrong clip, and mismatched camera projection', () => {
  for (const mutate of [
    ({ gltf }) => { gltf.scene.getObjectByName('WheelFL').name = 'Other'; },
    ({ gltf }) => { const extra = new Group(); extra.name = 'HeroCar'; gltf.scene.add(extra); },
    ({ gltf }) => { gltf.animations[0].name = 'Other'; },
    ({ manifest }) => { manifest.expected.camera.projection[0] += 1; },
  ]) {
    const input = fixture();
    mutate(input);
    assert.throws(() => createSceneBundle(input.gltf, input.manifest));
  }
});

test('rejects unsafe seek values rather than forwarding them to the mixer', () => {
  const { gltf, manifest } = fixture();
  const bundle = createSceneBundle(gltf, manifest);
  for (const value of [-1, 6, NaN, Infinity, '2.5']) {
    assert.throws(() => bundle.samplePose(value));
  }
  bundle.dispose();
});

test('rejects malformed GLB before invoking the loader', () => {
  assert.throws(() => inspectGlb(new ArrayBuffer(4)), /GLB/);
});

test('rejects missing, mistimed, nonfinite or discontinuous motion tracks', () => {
  for (const mutate of [
    gltf => gltf.animations[0].tracks.pop(),
    gltf => { gltf.animations[0].tracks[0].times[50] += 0.01; },
    gltf => { gltf.animations[0].tracks[1].values[20] = NaN; },
    gltf => { const v = gltf.animations[0].tracks[2].values; v.set(v.slice(40, 44), 80); },
  ]) {
    const { gltf, manifest } = fixture();
    mutate(gltf);
    assert.throws(() => createSceneBundle(gltf, manifest), /motion|sample|continuity|track/i);
  }
});
