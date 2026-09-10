import './viewer.css';
import { loadScene } from './scene.js';
import { createViewer } from './viewer.js';

const boot = window.__streetSceneBoot;
const canvas = document.querySelector('#scene-canvas');
const container = document.querySelector('#scene-viewport');
let viewer;
let bundle;
let seconds = 0;
let resolveReady, rejectReady;
const ready = new Promise((resolve, reject) => { resolveReady = resolve; rejectReady = reject; });
ready.catch(() => {});
boot.onFailure(() => {
  viewer?.dispose();
  if (!viewer) bundle?.dispose();
  rejectReady(new Error('Interactive scene failed; reload to recover'));
});

if (new URLSearchParams(location.search).get('capture') === '1') {
  function requireReady() {
    if (boot.phase !== 'ready') throw new Error('Capture requires a ready scene');
  }
  window.__streetSceneCapture = Object.freeze({
    ready,
    seek(value) {
      requireReady();
      bundle.samplePose(value);
      seconds = value;
    },
    renderOnce() { requireReady(); viewer.renderOnce(); },
    snapshot() {
      return {
        assetSha256: bundle?.manifest.asset.sha256 ?? null,
        phase: boot.phase, transport: 'paused', mode: 'authored', seconds,
        ...(viewer?.diagnostics() ?? { rendered: false }),
        load: bundle?.metrics,
      };
    },
  });
}

try {
  bundle = await loadScene(new URL('../assets/interactive/scene-manifest.json', document.baseURI),
    { signal: boot.signal });
  if (boot.phase === 'failed') {
    bundle.dispose();
  } else {
    viewer = await createViewer({ canvas, container, bundle, onError: boot.fail });
    if (boot.phase === 'failed') viewer.dispose();
    else { boot.markReady(); resolveReady(); }
  }
} catch (error) {
  boot.fail(error);
}
