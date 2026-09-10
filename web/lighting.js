import {
  Color, DataTexture, FloatType, RGBAFormat, EquirectangularReflectionMapping,
  PMREMGenerator, Quaternion, Vector3,
} from 'three';

export function createLighting(renderer, scene, sun, settings, mobile) {
  const direction = new Vector3(0, 0, -1)
    .applyQuaternion(sun.getWorldQuaternion(new Quaternion())).normalize();
  if (direction.distanceTo(new Vector3(...settings.sunDirection)) > 1e-5) {
    throw new Error('Authored sun direction differs from the source assertion');
  }
  sun.intensity = settings.sunIntensity;
  sun.castShadow = true;
  sun.shadow.mapSize.setScalar(mobile ? settings.shadow.mobileMapSize : settings.shadow.mapSize);
  const [left, right, bottom, top, near, far] = settings.shadow.bounds;
  Object.assign(sun.shadow.camera, { left, right, bottom, top, near, far });
  sun.shadow.camera.updateProjectionMatrix();
  sun.shadow.bias = settings.shadow.bias;
  sun.shadow.normalBias = settings.shadow.normalBias;
  scene.background = new Color(...settings.background);
  const width = 128, height = 64;
  const data = new Float32Array(width * height * 4);
  const sky = new Color(...settings.skyColor);
  const ground = new Color(...settings.groundColor);
  for (let y = 0; y < height; y++) {
    const elevation = Math.cos(Math.PI * (y + 0.5) / height);
    const color = ground.clone().lerp(sky, Math.min(1, Math.max(0, elevation * 1.8 + 0.45)));
    for (let x = 0; x < width; x++) {
      data.set([color.r, color.g, color.b, 1], (y * width + x) * 4);
    }
  }
  const texture = new DataTexture(data, width, height, RGBAFormat, FloatType);
  texture.mapping = EquirectangularReflectionMapping;
  texture.needsUpdate = true;
  const generator = new PMREMGenerator(renderer);
  const environment = generator.fromEquirectangular(texture);
  generator.dispose();
  texture.dispose();
  scene.environment = environment.texture;
  scene.environmentIntensity = settings.environmentIntensity;
  let disposed = false;
  return {
    environmentBytesEstimate: environment.width * environment.height * 8,
    dispose() {
      if (disposed) return;
      disposed = true;
      scene.environment = null;
      environment.dispose();
      sun.shadow.dispose();
    },
  };
}
