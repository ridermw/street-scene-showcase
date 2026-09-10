import { Document } from '@gltf-transform/core';
import { KHRLightsPunctual } from '@gltf-transform/extensions';
import { PerspectiveCamera } from 'three';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { manifestFixture } from './fixtures.mjs';
import { createIO, hash, SOURCE_SHA256 } from '../../tools/check-publication.mjs';

export function assetFixture() {
  const manifest = manifestFixture();
  manifest.sourceSceneSha256 = SOURCE_SHA256;
  manifest.lighting.sunDirection = [0, 0, -1];
  manifest.materials[0].generatedTextures = [];
  Object.assign(manifest.statistics, { triangles: 1, materials: 1, images: 1, logicalObjects: 1 });
  const camera = new PerspectiveCamera(manifest.expected.camera.yfov * 180 / Math.PI, 16 / 9, 0.1, 800);
  manifest.expected.camera.projection = camera.projectionMatrix.toArray();
  const document = new Document();
  const buffer = document.createBuffer();
  const accessor = (type, values) => document.createAccessor().setType(type).setBuffer(buffer).setArray(values);
  const scene = document.createScene('Scene');
  document.getRoot().setDefaultScene(scene);
  const nodes = {};
  for (const name of ['ChaseCamera', 'HeroCar', 'Sun', 'WheelFL', 'WheelFR', 'WheelRL', 'WheelRR']) {
    nodes[name] = document.createNode(name);
    if (name.startsWith('Wheel')) nodes.HeroCar.addChild(nodes[name]);
    else scene.addChild(nodes[name]);
  }
  nodes.ChaseCamera.setCamera(document.createCamera().setType('perspective')
    .setYFov(manifest.expected.camera.yfov).setAspectRatio(16 / 9).setZNear(0.1).setZFar(800));
  const lights = document.createExtension(KHRLightsPunctual);
  nodes.Sun.setExtension(KHRLightsPunctual.EXTENSION_NAME, lights.createLight().setType('directional'));
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC', 'base64');
  const texture = document.createTexture('Fixture-color').setMimeType('image/png').setImage(png);
  const material = document.createMaterial('Material').setBaseColorTexture(texture);
  const primitive = document.createPrimitive().setMaterial(material)
    .setIndices(accessor('SCALAR', new Uint16Array([0, 1, 2])))
    .setAttribute('POSITION', accessor('VEC3', new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0])))
    .setAttribute('NORMAL', accessor('VEC3', new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1])))
    .setAttribute('TEXCOORD_0', accessor('VEC2', new Float32Array([0, 0, 1, 0, 0, 1])));
  const geometry = document.createNode('Geometry').setMesh(document.createMesh().addPrimitive(primitive));
  nodes.HeroCar.addChild(geometry);
  const animation = document.createAnimation('StreetSequence');
  const times = accessor('SCALAR', Float32Array.from({ length: 120 }, (_, i) => i / 24));
  for (const name of ['ChaseCamera', 'HeroCar', 'WheelFL', 'WheelFR', 'WheelRL', 'WheelRR']) {
    const wheel = name.startsWith('Wheel');
    const values = [];
    for (let i = 0; i < 120; i++) {
      const angle = -17.5 / 0.36 * i / 119;
      values.push(...(wheel ? [Math.sin(angle / 2), 0, 0, Math.cos(angle / 2)] : [0, 0, -17.5 * i / 119]));
    }
    const sampler = document.createAnimationSampler().setInput(times)
      .setOutput(accessor(wheel ? 'VEC4' : 'VEC3', new Float32Array(values))).setInterpolation('LINEAR');
    animation.addSampler(sampler).addChannel(document.createAnimationChannel()
      .setTargetNode(nodes[name]).setTargetPath(wheel ? 'rotation' : 'translation').setSampler(sampler));
  }
  return { document, manifest, nodes, primitive, geometry, scene, texture };
}

export function mutateGlb(bytes, mutate) {
  const buffer = Buffer.from(bytes);
  const length = buffer.readUInt32LE(12);
  const json = JSON.parse(buffer.subarray(20, 20 + length));
  mutate(json);
  let text = Buffer.from(JSON.stringify(json));
  text = Buffer.concat([text, Buffer.alloc((4 - text.length % 4) % 4, 32)]);
  const binary = buffer.subarray(20 + length);
  const header = Buffer.from(buffer.subarray(0, 20));
  header.writeUInt32LE(20 + text.length + binary.length, 8);
  header.writeUInt32LE(text.length, 12);
  return Buffer.concat([header, text, binary]);
}

export async function writeAssetFixture(directory, fixture = assetFixture()) {
  await mkdir(directory);
  const bytes = await createIO().writeBinary(fixture.document);
  const sha256 = hash(bytes);
  fixture.manifest.asset = { bytes: bytes.length, sha256, file: `attempt-23.${sha256}.glb` };
  fixture.manifest.statistics.geometryBytes = fixture.document.getRoot().listAccessors()
    .reduce((sum, item) => sum + item.getArray().byteLength, 0);
  fixture.manifest.statistics.textureBytes = fixture.texture.getImage().byteLength;
  await writeFile(path.join(directory, fixture.manifest.asset.file), bytes);
  await writeFile(path.join(directory, 'scene-manifest.json'), JSON.stringify(fixture.manifest));
  await writeFile(path.join(directory, 'THIRD_PARTY_NOTICES.txt'), [
    'Three.js\n', await readFile(new URL('../../node_modules/three/LICENSE', import.meta.url), 'utf8'),
    '\nmeshoptimizer\n', await readFile(new URL('../../node_modules/meshoptimizer/LICENSE.md', import.meta.url), 'utf8'),
  ].join('\n'));
  return fixture;
}
