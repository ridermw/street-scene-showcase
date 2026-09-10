export function manifestFixture() {
  const hash = 'a'.repeat(64);
  return {
    schemaVersion: 1,
    design: 'attempt-23',
    sourceSceneSha256: hash,
    asset: { file: `attempt-23.${hash}.glb`, sha256: hash, bytes: 1024 },
    animation: {
      clip: 'StreetSequence', fps: 24, frameStart: 1, frameEnd: 120,
      motionEndSeconds: 119 / 24, durationSeconds: 5,
    },
    roles: {
      camera: 'ChaseCamera', hero: 'HeroCar', sun: 'Sun',
      wheels: { frontLeft: 'WheelFL', frontRight: 'WheelFR', rearLeft: 'WheelRL', rearRight: 'WheelRR' },
    },
    expected: {
      camera: { aspect: 16 / 9, yfov: 0.534218, near: 0.1, far: 800, projection: Array(16).fill(0) },
      samples: 120, travelMeters: 17.5, wheelRadians: -17.5 / 0.36,
    },
    lighting: {
      sunDirection: [0.7, -1, -0.22], sunIntensity: 6, environmentIntensity: 0.7,
      skyColor: [0.5, 0.65, 0.9], groundColor: [0.12, 0.1, 0.08],
      background: [0.208, 0.336, 0.512], exposure: 2 ** 0.3,
      shadow: {
        mapSize: 2048, mobileMapSize: 1024,
        bounds: [-28, 28, -40, 40, 0.1, 150], bias: -0.0001, normalBias: 0.025,
      },
    },
    materials: [{
      id: 'Bricks059', sourceUrl: 'https://ambientcg.com/a/Bricks059',
      license: 'CC0-1.0', licenseUrl: 'https://creativecommons.org/publicdomain/zero/1.0/',
      inputHashes: { color: hash, roughness: hash, height: hash },
      tileMeters: 1.05, recipeVersion: 1,
      generatedTextures: [{ name: 'brick-normal', sha256: hash, width: 1024, height: 1024, usage: 'normal' }],
      approximations: ['Height-derived tangent normals approximate the source bump.'],
    }],
    statistics: {
      triangles: 929308, materials: 88, images: 7, logicalObjects: 286,
      textObjects: 7, geometryBytes: 25000000, textureBytes: 7000000,
    },
    limits: {
      sceneBytes: 30 * 1024 ** 2, bundleGzipBytes: 1024 ** 2,
      triangles: 1100000, drawCalls: 300, desktopDpr: 1.5, mobileDpr: 1,
    },
  };
}
