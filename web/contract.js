/**
 * @typedef {{file:string, sha256:string, bytes:number}} SceneAsset
 * @typedef {{clip:string, fps:number, frameStart:number, frameEnd:number,
 * motionEndSeconds:number, durationSeconds:number}} SceneAnimation
 * @typedef {{camera:string, hero:string, sun:string,
 * wheels:{frontLeft:string, frontRight:string, rearLeft:string, rearRight:string}} SceneRoles
 * @typedef {{schemaVersion:1, design:'attempt-23', sourceSceneSha256:string,
 * asset:SceneAsset, animation:SceneAnimation, roles:SceneRoles,
 * expected:object, lighting:object, materials:object[], statistics:object, limits:object}} SceneManifest
 * @typedef {{state:'paused'|'playing'|'ended', seconds:number}} PlaybackSnapshot
 * @typedef {{assetSha256:string, phase:string, transport:string, mode:string,
 * seconds:number, rendered:boolean, cssWidth:number, cssHeight:number,
 * pixelWidth:number, pixelHeight:number, dpr:number}} CaptureSnapshot
 */

function requireValue(condition, path, description) {
  if (!condition) throw new Error(`Invalid manifest ${path}: ${description}`);
}

const literal = expected => (value, path) =>
  requireValue(value === expected, path, `expected ${expected}`);
const number = (min = -Infinity, max = Infinity) => (value, path) =>
  requireValue(typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max,
    path, 'expected finite number in range');
const integer = (min = 0, max = Number.MAX_SAFE_INTEGER) => (value, path) => {
  number(min, max)(value, path);
  requireValue(Number.isSafeInteger(value), path, 'expected integer');
};
const hash = (value, path) =>
  requireValue(typeof value === 'string' && /^[a-f0-9]{64}$/.test(value), path, 'expected SHA256');
const name = (value, path) =>
  requireValue(typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/.test(value),
    path, 'expected safe name');
const text = (value, path) =>
  requireValue(typeof value === 'string' && value.length > 0 && value.length <= 500
    && !/[/\\]|file:|run-\d{8}|[\u0000-\u001f]/i.test(value), path, 'unsafe descriptive text');
const nullable = rule => (value, path) => { if (value !== null) rule(value, path); };
const list = (rule, length) => (value, path) => {
  requireValue(Array.isArray(value) && (length === undefined || value.length === length),
    path, 'expected array with declared dimensions');
  value.forEach((item, index) => rule(item, `${path}[${index}]`));
};
const record = shape => (value, path) => {
  requireValue(value !== null && typeof value === 'object' && !Array.isArray(value),
    path, 'expected record');
  for (const key of Object.keys(value)) {
    requireValue(Object.hasOwn(shape, key), `${path}.${key}`, 'unknown field');
  }
  for (const [key, rule] of Object.entries(shape)) {
    requireValue(Object.hasOwn(value, key), `${path}.${key}`, 'missing field');
    rule(value[key], `${path}.${key}`);
  }
};
const allowedUrl = values => (value, path) =>
  requireValue(values.includes(value), path, 'URL is not allowlisted');

const sourceUrls = [
  'https://ambientcg.com/a/Bricks059', 'https://ambientcg.com/a/Asphalt012',
  'https://github.com/ridermw/street-scene-showcase',
];
const material = record({
  id: name, sourceUrl: allowedUrl(sourceUrls), license: text,
  licenseUrl: nullable(allowedUrl(['https://creativecommons.org/publicdomain/zero/1.0/'])),
  inputHashes: record({ color: nullable(hash), roughness: nullable(hash), height: nullable(hash) }),
  tileMeters: nullable(number(0.001, 100)), recipeVersion: literal(1),
  generatedTextures: list(record({
    name, sha256: hash, width: integer(1, 4096), height: integer(1, 4096),
    usage: allowedUrl(['color', 'normal', 'roughness', 'carbon']),
  })),
  approximations: list(text),
});
const schema = record({
  schemaVersion: literal(1), design: literal('attempt-23'), sourceSceneSha256: hash,
  asset: record({ file: name, sha256: hash, bytes: integer(1) }),
  animation: record({
    clip: literal('StreetSequence'), fps: literal(24), frameStart: literal(1), frameEnd: literal(120),
    motionEndSeconds: literal(119 / 24), durationSeconds: literal(5),
  }),
  roles: record({
    camera: literal('ChaseCamera'), hero: literal('HeroCar'), sun: literal('Sun'),
    wheels: record({
      frontLeft: literal('WheelFL'), frontRight: literal('WheelFR'),
      rearLeft: literal('WheelRL'), rearRight: literal('WheelRR'),
    }),
  }),
  expected: record({
    camera: record({
      aspect: literal(16 / 9), yfov: number(0.01, Math.PI - 0.01),
      near: number(0.001, 1), far: number(1, 10000), projection: list(number(), 16),
    }),
    samples: literal(120), travelMeters: literal(17.5), wheelRadians: number(-49, -48),
  }),
  lighting: record({
    sunDirection: list(number(-1, 1), 3), sunIntensity: number(0, 20),
    environmentIntensity: number(0, 10), skyColor: list(number(0, 10), 3),
    groundColor: list(number(0, 10), 3), background: list(number(0, 1), 3),
    exposure: number(0.01, 10),
    shadow: record({
      mapSize: literal(2048), mobileMapSize: literal(1024), bounds: list(number(-1000, 1000), 6),
      bias: number(-0.01, 0.01), normalBias: number(0, 1),
    }),
  }),
  materials: list(material),
  statistics: record({
    triangles: integer(1), materials: integer(1), images: integer(1),
    logicalObjects: integer(1), textObjects: literal(7), geometryBytes: integer(1),
    textureBytes: integer(1),
  }),
  limits: record({
    sceneBytes: literal(30 * 1024 ** 2), bundleGzipBytes: literal(1024 ** 2),
    triangles: literal(1100000), drawCalls: literal(300),
    desktopDpr: literal(1.5), mobileDpr: literal(1),
  }),
});

/** @param {unknown} value @returns {SceneManifest} */
export function validateManifest(value) {
  schema(value, 'scene');
  requireValue(value.asset.file === `attempt-23.${value.asset.sha256}.glb`,
    'asset.file', 'must name the content-addressed model');
  requireValue(value.expected.camera.near < value.expected.camera.far,
    'expected.camera', 'near must precede far');
  requireValue(value.materials.length > 0, 'materials', 'provenance is required');
  return value;
}
