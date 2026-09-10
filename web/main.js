import './viewer.css';
import { loadScene } from './scene.js';
import { createViewer } from './viewer.js';
import { createPlayback } from './playback.js';

const boot = window.__streetSceneBoot;
const canvas = document.querySelector('#scene-canvas');
const container = document.querySelector('#scene-viewport');
const buttons = Object.fromEntries(['play', 'restart', 'inspect'].map(id => [id, document.getElementById(id)]));
const bindings = new AbortController();
let viewer, bundle, playback, released = false;
let resolveReady, rejectReady;
const ready = new Promise((resolve, reject) => { resolveReady = resolve; rejectReady = reject; });
ready.catch(() => {});

function release() {
  if (released) return;
  released = true;
  viewer?.stopRendering();
  bindings.abort();
  if (viewer) viewer.dispose();
  else bundle?.dispose();
}

boot.onFailure(() => {
  try { release(); }
  finally { rejectReady(new Error('Interactive scene failed; reload to recover')); }
});

function renderState() {
  if (boot.phase !== 'ready' || !viewer) return;
  const { state, mode, seconds } = viewer.snapshot();
  const inspecting = mode === 'inspection';
  buttons.play.disabled = inspecting;
  buttons.restart.disabled = inspecting;
  buttons.inspect.disabled = false;
  buttons.play.textContent = state === 'playing' ? 'Pause' : 'Play';
  buttons.inspect.textContent = inspecting ? 'Return to authored camera' : 'Inspect scene';
  buttons.inspect.setAttribute('aria-pressed', String(inspecting));
  document.querySelector('#inspection-help').hidden = !inspecting;
  document.querySelector('#scene-status').textContent = inspecting
    ? 'Inspection mode. Playback is paused.'
    : state === 'playing' ? 'Playing the five-second scene.'
      : state === 'ended' ? 'Finished. Play or Restart runs the scene again.'
        : `Paused at ${seconds.toFixed(2)} seconds.`;
}

function act(type, value) {
  try { viewer.dispatch(type, value); renderState(); }
  catch (error) { boot.fail(error); }
}

if (new URLSearchParams(location.search).get('capture') === '1') {
  function requireReady() {
    if (boot.phase !== 'ready' || released || !viewer) throw new Error('Capture requires a ready scene');
  }
  window.__streetSceneCapture = Object.freeze({
    ready,
    seek(value) { requireReady(); viewer.dispatch('seek', value); },
    renderOnce() { requireReady(); viewer.renderOnce(); },
    snapshot() {
      requireReady();
      const state = viewer.snapshot();
      return { assetSha256: bundle.manifest.asset.sha256, phase: boot.phase,
        transport: state.state, mode: state.mode, seconds: state.seconds,
        ...viewer.diagnostics(), load: bundle.metrics };
    },
  });
}

try {
  bundle = await loadScene(new URL('../assets/interactive/scene-manifest.json', document.baseURI), { signal: boot.signal });
  if (boot.phase === 'failed' || released) bundle.dispose();
  else {
    playback = createPlayback({ durationSeconds: bundle.manifest.animation.durationSeconds });
    viewer = await createViewer({ canvas, container, bundle, playback, onState: renderState, onError: boot.fail, signal: boot.signal });
    if (boot.phase === 'failed' || released) viewer.dispose();
    else {
      const options = { signal: bindings.signal };
      buttons.play.addEventListener('click', () => act(playback.snapshot().state === 'playing' ? 'pause' : 'play'), options);
      buttons.restart.addEventListener('click', () => act('restart'), options);
      buttons.inspect.addEventListener('click', () => act('inspection', viewer.snapshot().mode !== 'inspection'), options);
      document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && viewer.snapshot().mode === 'inspection') {
          event.preventDefault();
          act('inspection', false);
          buttons.inspect.focus();
        }
      }, options);
      window.addEventListener('pagehide', release, { once: true });
      window.addEventListener('pageshow', event => {
        if (event.persisted && released) boot.fail(new Error('The scene was unloaded; reload to recover'));
      });
      boot.markReady();
      renderState();
      resolveReady();
    }
  }
} catch (error) {
  boot.fail(error);
}
