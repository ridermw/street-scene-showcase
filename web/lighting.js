import {
  Color, DataTexture, FloatType, RGBAFormat, EquirectangularReflectionMapping,
  PMREMGenerator, Quaternion, Vector3, DirectionalLight,
} from 'three';

export function configureShadowFrustum(sun, settings, center) {
  const direction = new Vector3(0, 0, -1).applyQuaternion(sun.getWorldQuaternion(new Quaternion())).normalize();
  const anchor = new DirectionalLight();
  anchor.position.copy(center).addScaledVector(direction, -settings.bounds[5] * 0.45);
  anchor.target.position.copy(center);
  anchor.updateMatrixWorld(true);
  anchor.target.updateMatrixWorld(true);
  const original = sun.shadow.updateMatrices;
  sun.shadow.updateMatrices = () => original.call(sun.shadow, anchor);
  const [left, right, bottom, top, near, far] = settings.bounds;
  Object.assign(sun.shadow.camera, { left, right, bottom, top, near, far });
  sun.shadow.camera.updateProjectionMatrix();
  return () => { sun.shadow.updateMatrices = original; anchor.dispose(); };
}

export function environmentPixels(settings) {
  const width = 128, height = 64;
  const data = new Float32Array(width * height * 4);
  const sky = new Color(...settings.skyColor);
  const ground = new Color(...settings.groundColor);
  for (let y = 0; y < height; y++) {
    const elevation = -Math.cos(Math.PI * (y + 0.5) / height);
    for (let x = 0; x < width; x++) {
      const lateral = Math.abs(Math.cos(2 * Math.PI * (x + 0.5) / width)) * Math.sqrt(1 - elevation ** 2);
      const visibility = Math.min(1, Math.max(0, (elevation - 1.8 * lateral) / 0.12));
      const color = ground.clone().lerp(sky, visibility * visibility * (3 - 2 * visibility));
      data.set([color.r, color.g, color.b, 1], (y * width + x) * 4);
    }
  }
  return { width, height, data };
}

export function createLighting(renderer, scene, sun, settings, mobile, center) {
  const direction = new Vector3(0, 0, -1)
    .applyQuaternion(sun.getWorldQuaternion(new Quaternion())).normalize();
  if (direction.distanceTo(new Vector3(...settings.sunDirection)) > 1e-5) {
    throw new Error('Authored sun direction differs from the source assertion');
  }
  sun.intensity = settings.sunIntensity;
  sun.castShadow = true;
  sun.shadow.mapSize.setScalar(mobile ? settings.shadow.mobileMapSize : settings.shadow.mapSize);
  const restoreShadow = configureShadowFrustum(sun, settings.shadow, center);
  sun.shadow.bias = settings.shadow.bias;
  sun.shadow.normalBias = settings.shadow.normalBias;
  scene.background = new Color(...settings.background);
  const { width, height, data } = environmentPixels(settings);
  const texture = new DataTexture(data, width, height, RGBAFormat, FloatType);
  texture.mapping = EquirectangularReflectionMapping;
  texture.needsUpdate = true;
  const generator = new PMREMGenerator(renderer);
  let environment;
  try { environment = generator.fromEquirectangular(texture); }
  catch (error) { restoreShadow(); throw error; }
  finally { generator.dispose(); texture.dispose(); }
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
      restoreShadow();
    },
  };
}
