import { AgXToneMapping, PCFShadowMap, Scene, SRGBColorSpace, WebGLRenderer } from 'three';
import { createLighting } from './lighting.js';

export function fitViewport(width, height, deviceDpr, coarse) {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null;
  const fittedWidth = Math.min(width, height * 16 / 9);
  return {
    width: fittedWidth, height: fittedWidth * 9 / 16,
    dpr: Math.min(deviceDpr, fittedWidth <= 640 || coarse ? 1 : 1.5),
  };
}

export async function createViewer({ canvas, container, bundle, onError }) {
  const context = canvas.getContext('webgl2', { antialias: true, alpha: false });
  if (!context) throw new Error('WebGL2 is unavailable');
  const renderer = new WebGLRenderer({ canvas, context, antialias: true });
  renderer.outputColorSpace = SRGBColorSpace;
  renderer.toneMapping = AgXToneMapping;
  renderer.toneMappingExposure = bundle.manifest.lighting.exposure;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = PCFShadowMap;
  const scene = new Scene();
  scene.add(bundle.root);
  let disposed = false;
  let rendered = false;
  let size;
  let mainCalls = 0, shadowCalls = 0;
  const coarse = matchMedia('(pointer: coarse)').matches;
  bundle.root.traverse(node => {
    if (!node.isMesh) return;
    node.castShadow = true;
    node.receiveShadow = true;
    node.onBeforeRender = () => { mainCalls++; };
    node.onBeforeShadow = () => { shadowCalls++; };
  });
  const lighting = createLighting(renderer, scene, bundle.roles.sun, bundle.manifest.lighting,
    container.clientWidth <= 640 || coarse);
  function resize() {
    size = fitViewport(container.clientWidth, container.clientHeight, devicePixelRatio, coarse);
    if (!size) return;
    renderer.setPixelRatio(size.dpr);
    renderer.setSize(size.width, size.height, false);
    bundle.camera.aspect = 16 / 9;
    bundle.camera.updateProjectionMatrix();
    renderOnce();
  }
  function renderOnce() {
    if (disposed) throw new Error('Viewer is disposed');
    if (!size) throw new Error('Viewer has no drawable viewport');
    mainCalls = 0;
    shadowCalls = 0;
    renderer.render(scene, bundle.camera);
    if (context.isContextLost()) throw new Error('WebGL context lost');
    rendered = true;
  }
  function contextLost(event) {
    event.preventDefault();
    onError(new Error('WebGL context lost'));
  }
  canvas.addEventListener('webglcontextlost', contextLost);
  const observer = new ResizeObserver(() => {
    if (disposed) return;
    try { resize(); } catch (error) { onError(error); }
  });
  observer.observe(container);
  try {
    size = fitViewport(container.clientWidth, container.clientHeight, devicePixelRatio, coarse);
    if (!size) throw new Error('Viewer has no drawable viewport');
    renderer.setPixelRatio(size.dpr);
    renderer.setSize(size.width, size.height, false);
    await renderer.compileAsync(scene, bundle.camera);
    renderOnce();
  } catch (error) {
    observer.disconnect();
    canvas.removeEventListener('webglcontextlost', contextLost);
    lighting.dispose();
    renderer.dispose();
    throw error;
  }
  return {
    renderOnce,
    diagnostics() {
      return {
        rendered, cssWidth: size.width, cssHeight: size.height,
        pixelWidth: canvas.width, pixelHeight: canvas.height, dpr: size.dpr,
        mainDrawCalls: mainCalls, shadowDrawCalls: shadowCalls,
        triangles: renderer.info.render.triangles,
        resources: { ...renderer.info.memory, programs: renderer.info.programs.length },
        projection: [...bundle.camera.projectionMatrix.elements],
        cameraPosition: bundle.camera.getWorldPosition(bundle.camera.position.clone()).toArray(),
        heroPosition: bundle.roles.hero.getWorldPosition(bundle.roles.hero.position.clone()).toArray(),
        wheelRotations: Object.fromEntries(Object.entries(bundle.roles.wheels)
          .map(([name, wheel]) => [name, wheel.quaternion.toArray()])),
        environmentBytesEstimate: lighting.environmentBytesEstimate,
      };
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      rendered = false;
      renderer.setAnimationLoop(null);
      observer.disconnect();
      canvas.removeEventListener('webglcontextlost', contextLost);
      lighting.dispose();
      bundle.dispose();
      renderer.dispose();
    },
  };
}
