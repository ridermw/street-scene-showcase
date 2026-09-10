import { AgXToneMapping, PCFShadowMap, Scene, SRGBColorSpace, Vector3, WebGLRenderer } from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { createLighting } from './lighting.js';

export function fitViewport(width, height, deviceDpr, coarse) {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null;
  if (!Number.isFinite(deviceDpr) || deviceDpr <= 0) throw new Error('Invalid device pixel ratio');
  const fittedWidth = Math.min(width, height * 16 / 9);
  return { width: fittedWidth, height: fittedWidth * 9 / 16,
    dpr: Math.min(deviceDpr, fittedWidth <= 640 || coarse ? 1 : 1.5) };
}

export function createCameraRig(authored, playback) {
  const inspection = authored.clone(false);
  let inspecting = false;
  return {
    inspection,
    get camera() { return inspecting ? inspection : authored; },
    get mode() { return inspecting ? 'inspection' : 'authored'; },
    setInspection(enabled) {
      if (typeof enabled !== 'boolean') throw new Error('Invalid inspection mode');
      if (enabled === inspecting) return;
      playback.pause();
      if (enabled) {
        inspection.copy(authored, false);
        authored.getWorldPosition(inspection.position);
        authored.getWorldQuaternion(inspection.quaternion);
        inspection.scale.setScalar(1);
        inspection.updateMatrixWorld(true);
      }
      inspecting = enabled;
    },
  };
}

export function createTeardown(stages) {
  let disposed = false;
  return () => {
    if (disposed) return;
    disposed = true;
    const errors = [];
    for (const stage of stages) {
      try { stage(); } catch (error) { errors.push(error); }
    }
    if (errors.length) throw new AggregateError(errors, 'Viewer teardown failed');
  };
}

export async function createViewer({ canvas, container, bundle, playback, onState, onError, signal }) {
  let renderer, observer, controls, lighting, context, size;
  let disposed = false, ready = false, rendered = false, completedFrames = 0;
  let rejectSetup = () => {};
  let mainCalls = 0, shadowCalls = 0, lastState = '';
  const listeners = new AbortController();
  const rig = createCameraRig(bundle.camera, playback);
  const scene = new Scene();
  scene.add(bundle.root);
  const dispose = createTeardown([
    () => { disposed = true; ready = false; rendered = false; renderer?.setAnimationLoop(null); playback.pause(); },
    () => { observer?.disconnect(); listeners.abort(); },
    () => controls?.dispose(),
    () => lighting?.dispose(),
    () => { scene.remove(bundle.root); bundle.dispose(); },
    () => { renderer?.dispose(); renderer?.forceContextLoss(); },
  ]);
  const fail = error => onError(error);
  const coarse = () => matchMedia('(pointer: coarse)').matches;
  const snapshot = () => ({ ...playback.snapshot(), mode: rig.mode });
  function notify(force = false) {
    const value = snapshot();
    const key = `${value.state}:${value.mode}`;
    if (force || key !== lastState) { lastState = key; onState(value); }
  }
  function renderOnce() {
    if (disposed) throw new Error('Viewer is disposed');
    if (!size) throw new Error('Viewer has no drawable viewport');
    mainCalls = 0;
    shadowCalls = 0;
    renderer.render(scene, rig.camera);
    if (context.isContextLost()) throw new Error('WebGL context lost');
    rendered = true;
    completedFrames++;
  }
  function resize() {
    if (disposed) return;
    const fitted = fitViewport(container.clientWidth, container.clientHeight, devicePixelRatio, coarse());
    if (!fitted) {
      size = null;
      playback.pause();
      notify();
      return;
    }
    size = fitted;
    renderer.setPixelRatio(size.dpr);
    renderer.setSize(size.width, size.height, false);
    canvas.style.width = `${size.width}px`;
    canvas.style.height = `${size.height}px`;
    for (const camera of [bundle.camera, rig.inspection]) {
      camera.aspect = 16 / 9;
      camera.updateProjectionMatrix();
    }
    if (ready) renderOnce();
  }
  function dispatch(type, value) {
    if (!ready || disposed) throw new Error('Viewer is not ready');
    if (type === 'inspection') {
      rig.setInspection(value);
      controls.enabled = value;
      canvas.style.touchAction = value ? 'none' : 'pan-y';
      if (value) {
        const distance = bundle.camera.getWorldPosition(new Vector3())
          .distanceTo(bundle.roles.hero.getWorldPosition(new Vector3()));
        controls.target.copy(rig.inspection.position).addScaledVector(rig.inspection.getWorldDirection(new Vector3()), distance);
        controls.update();
      }
    } else if (type === 'pause') playback.pause();
    else {
      if (rig.mode === 'inspection') throw new Error('Playback is disabled during inspection');
      if (type === 'play') playback.play();
      else if (type === 'restart') playback.restart();
      else if (type === 'seek') { playback.seek(value); playback.pause(); }
      else throw new Error('Unknown viewer action');
    }
    bundle.samplePose(playback.snapshot().seconds);
    renderOnce();
    notify(true);
    return snapshot();
  }
  try {
    signal?.throwIfAborted();
    signal?.addEventListener('abort', () => {
      rejectSetup(signal.reason);
      try { dispose(); } catch (error) { console.error('Viewer cleanup failed', error); }
    }, { once: true, signal: listeners.signal });
    context = canvas.getContext('webgl2', { antialias: true, alpha: false });
    if (!context) throw new Error('WebGL2 is unavailable');
    if (context.isContextLost()) throw new Error('WebGL context lost during startup');
    renderer = new WebGLRenderer({ canvas, context, antialias: true });
    renderer.debug.onShaderError = (gl, program) => { throw new Error(`Scene shader compilation failed: ${gl.getProgramInfoLog(program)}`); };
    renderer.outputColorSpace = SRGBColorSpace;
    renderer.toneMapping = AgXToneMapping;
    renderer.toneMappingExposure = bundle.manifest.lighting.exposure;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = PCFShadowMap;
    bundle.root.traverse(node => {
      if (!node.isMesh) return;
      node.castShadow = true;
      node.receiveShadow = true;
      node.onBeforeRender = () => { mainCalls++; };
      node.onBeforeShadow = () => { shadowCalls++; };
    });
    const center = bundle.roles.hero.getWorldPosition(new Vector3());
    center.y += 1;
    center.z -= bundle.manifest.expected.travelMeters / 2;
    lighting = createLighting(renderer, scene, bundle.roles.sun, bundle.manifest.lighting,
      container.clientWidth <= 640 || coarse(), center);
    controls = new OrbitControls(rig.inspection, canvas);
    controls.enabled = false;
    controls.enableDamping = true;
    controls.minDistance = 2;
    controls.maxDistance = 35;
    controls.maxPolarAngle = Math.PI * 0.49;
    controls.listenToKeyEvents(canvas);
    canvas.style.touchAction = 'pan-y';
    const options = { signal: listeners.signal };
    canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); fail(new Error('WebGL context lost')); }, options);
    const onResize = () => { try { resize(); } catch (error) { fail(error); } };
    observer = new ResizeObserver(onResize);
    observer.observe(container);
    window.addEventListener('resize', onResize, options);
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) { playback.pause(); notify(); }
    }, options);
    resize();
    if (!size) throw new Error('Viewer has no drawable viewport');
    signal?.throwIfAborted();
    await new Promise((resolve, reject) => {
      rejectSetup = reject;
      Promise.resolve().then(() => renderer.compileAsync(scene, bundle.camera)).then(resolve, reject);
    });
    signal?.throwIfAborted();
    if (disposed) throw new Error('Viewer was disposed during setup');
    ready = true;
    renderOnce();
    renderer.setAnimationLoop(timestamp => {
      if (disposed || !size) return;
      try {
        if (playback.snapshot().state === 'playing') {
          const state = playback.tick(timestamp);
          bundle.samplePose(state.seconds);
          renderOnce();
          notify();
        } else if (rig.mode === 'inspection' && controls.update()) renderOnce();
      } catch (error) { fail(error); }
    });
    notify();
  } catch (error) {
    try { dispose(); } catch (cleanupError) { throw new AggregateError([error, cleanupError], 'Viewer setup and teardown failed'); }
    throw error;
  }
  return {
    renderOnce, dispatch, snapshot, dispose,
    stopRendering: () => renderer.setAnimationLoop(null),
    setInspection: enabled => dispatch('inspection', enabled),
    diagnostics() {
      if (!ready || disposed) throw new Error('Viewer diagnostics require readiness');
      const rect = canvas.getBoundingClientRect();
      return {
        rendered, completedFrames, cssWidth: rect.width, cssHeight: rect.height,
        pixelWidth: canvas.width, pixelHeight: canvas.height, dpr: size.dpr,
        mainDrawCalls: mainCalls, shadowDrawCalls: shadowCalls,
        triangles: renderer.info.render.triangles,
        resources: { ...renderer.info.memory, programs: renderer.info.programs.length },
        projection: [...bundle.camera.projectionMatrix.elements],
        cameraPosition: bundle.camera.getWorldPosition(new Vector3()).toArray(),
        activeCameraPosition: rig.camera.getWorldPosition(new Vector3()).toArray(),
        heroPosition: bundle.roles.hero.getWorldPosition(new Vector3()).toArray(),
        wheelRotations: Object.fromEntries(Object.entries(bundle.roles.wheels).map(([name, wheel]) => [name, wheel.quaternion.toArray()])),
        environmentBytesEstimate: lighting.environmentBytesEstimate,
        shadowBytesEstimate: bundle.roles.sun.shadow.mapSize.x ** 2 * 8,
        decodedGeometryBytes: bundle.metrics.decodedGeometryBytes,
        estimatedTextureBytes: bundle.metrics.estimatedTextureBytes,
      };
    },
  };
}
