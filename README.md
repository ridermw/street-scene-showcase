# Street scene

An original procedural Blender street scene with a red car and a five second camera move.
Attempt 23 is the selected final design.

**[Watch the final video](https://ridermw.github.io/street-scene-showcase/)**
| **[Concept art and references](https://ridermw.github.io/street-scene-showcase/concept.html)**
| **[Browse the attempts](https://ridermw.github.io/street-scene-showcase/attempts.html)**

![Selected scene, attempt 23](docs/assets/final.jpg)

The final video contains 120 frames at 1920 by 1080 and 24 fps.
The gallery includes 22 retained previews from attempts 1 through 23.
No preview was retained for attempt 4.
The concept page shows early scene studies and links to the external visual reference.
No separate drawn concept art was produced.

The selected design keeps the improved hero car and window design B.
It restores the earlier parked vehicle geometry.
The minivan shape and distant architecture remain below the reference target.
Selection of this design does not establish a reference quality match.

## Contents

| Path | Content |
|---|---|
| `docs/` | GitHub Pages site, final video, and attempt gallery |
| `blender/` | Geometry, scene construction, and capture scripts |
| `pipeline/` | Resource limits, ownership checks, and evidence records |
| `tools/` | Video encoding and review packet tools |
| `tests/` | Pipeline tests and Blender inspection scripts |
| `configs/street_scene.example.json` | Configuration example without machine paths |

This public export excludes private plans, review transcripts, machine paths,
raw run logs, and the downloaded reference video.
It does not include the private delivery archive.

## Run the tests

Use Python 3.11 or later, FFmpeg, and FFprobe.
Image preparation uses Pillow, listed in `requirements.txt`.

```sh
python3 -m unittest discover -s tests
```

## Build a new scene

The pipeline targets Blender 5.2.1 LTS on macOS with Metal.
The capture script does not support other GPU backends.
The public configuration is deliberately inactive.
Do not start a render until you set the intended time and storage limits.

1. Copy `configs/street_scene.example.json` to `configs/street_scene.json`.
2. Set `data_root`, a new `run_id`, and explicit UTC start and deadline values.
3. Set the storage and free space limits for your machine.
4. Download the CC0 `Bricks059` and `Asphalt012` JPG material sets from ambientCG.
5. Put each set's Color, Roughness, and Displacement JPGs in
   `DATA_ROOT/RUN_ID/assets/bricks` and `DATA_ROOT/RUN_ID/assets/asphalt`.
6. Run construction through the resource supervisor.

```sh
python3 -m pipeline.job --log build-attempt-01.log -- \
  /Applications/Blender.app/Contents/MacOS/Blender \
  -b --factory-startup --python-exit-code 1 \
  -P blender/build_scene.py -- --attempt attempt-01
```

The supervisor permits one heavy job at a time and reserves the last five minutes.
It writes job logs inside the configured run directory, not the repository root.
Use only isolated Blender processes. Do not run construction inside an unrelated open scene.
Full sequence capture also requires current design approval and a capacity forecast.
The source preserves those controls; it does not bypass them for this public export.

Select `Hero car path`, `Chase camera path`, and `Afternoon sun direction`
to edit the generated scene. Save an editing copy first.

## Interactive interpretation (in development)

The interactive Three.js interpretation is not published yet. The final video,
concept page, gallery, and GitHub Pages `main:/docs` deployment remain unchanged.
Source/export preconditions, the first actual-scene browser slice, and independent
raw-export geometry/material/animation checks are implemented.
The raw diagnostic export contains 932,272 triangles, seven converted text objects,
seven embedded images, and all 120 samples on the six authored motion controls.
Its effective camera projection agrees with the source. Independent checks reopen
the frozen scene and compare every exported triangle, corner normal, material
assignment, all 120 control poses, and the full signed wheel revolutions.
They also exercise recessed glazing, attached trim, and recessed shoulder vents
on both source and reimported geometry. Additions and omissions are rejected.
Two clean corrected exports have identical GLB and derived-image hashes.

The corrected raw GLB is approximately 54.5 MiB, above the final 30 MiB package limit.
Lossless mesh compression, compatible resource deduplication and pixel-exact
PNG storage conversion now produce a validated **30,748,589-byte scene package**
(29.32 MiB), including its manifest and runtime notices. Two preparations match.
It retains 286 logical geometry objects and 932,272 triangles, with 53 compatible
materials and seven images. All original named nodes remain; no geometry batching,
precision reduction, filtering, decimation or texture downscaling was needed.
The package bounds main-pass draws at 288; the browser anchors measured 287,
284 and 275 calls. The complete viewer JavaScript is 185,416 bytes gzip.

`tools/optimize_png.py` implements the tested storage conversion using the
existing Pillow dependency. It uses exact palette indices only for images with
at most 256 distinct opaque colors; it does not reduce the color count, change
pixels, or downscale. Other images retain full color and alpha. It preserves
standard color-space chunks and removes descriptive metadata; embedded ICC
profiles require separate review and are rejected. JPEGs are not recompressed.
The actual compressed model loads through the bundled decoder under the production
prefix. Rejection tests cover malformed buffers, roles, projection, animation
continuity, provenance, metadata, resource budgets, stale approval and incomplete
publication copies. Portable review identity includes all candidate files and
canonical capture settings; relocation does not change it.

The integrated viewer has one playback/render loop, accessible Play/Pause,
Restart and inspection controls, a separate orbit camera, hidden-tab pausing,
responsive 16:9 sizing and bounded DPR. It restores the authored camera and
paused time after inspection, including the ended state. Startup and failure
use the independent HTML deadline and video fallback; recovery is a full reload.
Node and browser consumers share the same six-channel motion validation.

Lighting now uses a correctly oriented low-resolution procedural canyon
environment and fixed shadow coverage over the full motion, without moving the
authored sun or adding a rendered light. The background and exposure are calibrated
separately. Exact-size captures and control checks pass in WebKit and hardware-backed
Chromium on the local Apple M4 Pro.

The frozen candidate passes 48 browser cases across Chromium and WebKit.
Two intentional WebKit skips avoid duplicating the hardware benchmark and motion
recording; WebKit still runs all correctness cases. Fault injection covers missing
and stalled modules/assets/bodies, invalid model data, decoding and texture failure,
late bitmap disposal, unavailable WebGL and context loss. No-JavaScript and failed
startup both expose the preserved video without an empty scene blocking the page.
Mobile emulation tests exercise portrait/landscape layouts and DPR caps, not phone
hardware performance. WebKit's native media-placard icon errors also reproduce
on the unchanged video page under mobile emulation. Only that exact native
signature is classified and retained as a warning in those layout cases; other
console errors remain failures.

On September 10, 2026, Chromium `153.0.8010.12` using ANGLE Metal on an Apple M4 Pro
passed three warmed full-playback cycles at a 1280 by 720 CSS canvas, DPR 1.5 and
1920 by 1080 backing buffer. Cold startup was 391.8 ms, measured separately.

| Run | Completed frames / samples | FPS | Median / p95 / worst interval |
|---|---|---|---|
| 1 | 302 / 302 | 60.040 | 16.7 / 17.6 / 20.0 ms |
| 2 | 302 / 302 | 60.035 | 16.7 / 17.5 / 20.3 ms |
| 3 | 302 / 302 | 60.036 | 16.7 / 17.6 / 19.2 ms |

Each run stayed below 300 main-pass calls (maximum 287); shadow-pass maximum was
263. Counts remained stable at 246 geometries, 11 textures and five programs
through repeated restart and inspection. The browser reports 45,372,116 unique
geometry-buffer bytes and estimates 55,924,058 texture bytes, 344,064 environment
bytes and 33,554,432 shadow-target bytes. These are resource counters and estimates,
not exact total browser or GPU memory. Node's decoded accessor inventory also
includes animation data and totals 45,377,396 bytes.

Private, source-hash-verified 1920 by 1080 start/middle/end comparisons and a complete
motion/restart recording are retained with the exact candidate identity.
The chronological review covers all 205 recorded frames at 25 fps; it does not
replace the separately measured rendering throughput or explicit visual approval.
Compared with Cycles, absent indirect/contact shadows make vehicles look less
grounded, paint highlights/reflections are weaker or different, and the sky and
contrast are flatter. Shadow aliasing and reduced distant shadow coverage remain.
Finite-resolution bump and carbon conversion also remain approximations.
These differences are **not visually accepted**. Publication is blocked pending
explicit acceptance of this exact candidate or a decision to improve it.

`configs/gltf-export.example.json` is deliberately inactive. Before export or
material baking, obtain a new bounded allowance and save the active configuration
only in private task-owned staging. Specify timezone-aware start/deadline values,
positive integer storage-growth and free-space limits, one heavy job, the frozen
source and approved SHA256, and all read-only source roots. Set `data_root` to
owned staging and `run_id` to a new child directory. Never reuse an expired scene
construction allowance. The existing `pipeline.job --config` supervisor retains
its heavy-job lock, storage monitoring, pause handling, and five-minute reserve.
Export configurations identify themselves with `kind: "gltf-export"` so the
supervisor validates source and run boundaries before creating logs or locks.
The exporter restricts every output to that monitored run directory.

Exports must use new or empty directories strictly inside the owned staging
boundary, disjoint from the source directories. Parent traversal and source
aliases (including symlinks and hard links) are rejected. These checks are
preconditions, not a sandbox: keep staging exclusively task-owned. Do not save
over the frozen `.blend`, write into either source tree, or publish source
records, machine paths, intermediate receipts, or reference media.

Source frames 1 through 120 map to `0` through `119 / 24` seconds. The viewer will
hold the final pose until five seconds rather than stretch the sampled motion.
Generated candidates stay private until exact-artifact visual approval and the
complete browser, geometry, animation, and performance gates are satisfied.

```sh
python3 -m unittest discover -s tests -p 'test_export_contract.py'
```

The initial viewer pins Three.js `0.185.1`, Vite `8.2.2`, and Playwright `1.63.0`.
Use Node `22.23.1` and the committed lockfile. Build candidates only into private
staging while the release is incomplete:

```sh
npm ci
npm run test:unit
npm run build -- --outDir "$CANDIDATE_SITE/interactive/assets"
```

Prepare and validate a private scene package under the same active supervisor:

```sh
python3 -m pipeline.job --config "$EXPORT_CONFIG" --log prepare-asset.log -- \
  npm run prepare:asset -- --input "$RAW_GLB" --manifest "$RAW_MANIFEST" --output "$ASSET_CANDIDATE"
npm run check -- --site "$CANDIDATE_SITE"
```

Prepare the curated prefix fixture with the existing preview helper, then run
the browser suite against its loopback server in a second terminal. Choose
`BROWSER_OUTPUT` inside task-owned staging; reports must not go into the public site.
`WEBKIT_EXECUTABLE` can select an already installed task-owned WebKit runtime.
An absent runtime must be installed before its browser cases can pass.

```sh
npm run preview -- --site "$CANDIDATE_SITE"
BROWSER_OUTPUT="$BROWSER_REPORTS" \
  python3 -m pipeline.job --config "$EXPORT_CONFIG" --log browser-check.log -- \
  npm run test:browser
PUBLICATION_SITE="$CANDIDATE_SITE" python3 -m unittest discover -s tests -p test_publication.py
```

The default Python suite intentionally skips generated-release checks while
`docs` has no published model; the explicit staged-site run requires every file.
The preview helper serves only its curated copy, never the repository or raw export
root. Browser tests require full hardware-backed Chromium for the performance gate,
not a software-rendered headless shell. A passing build or a resource allowance is
not visual approval and does not authorize copying generated files into `docs`.

The public checker accounts for the complete scene package and every generated
JavaScript chunk together. It explicitly reports the Khronos validator's lack of
Meshopt inspection; independent decoding, exact accessor comparisons and the real
browser loader cover that extension. Generated files remain private until approval.

The isolated export requires the frozen scene's retained `scene.json` and packed
source images. With an authorized private configuration and a new output directory:

```sh
python3 -m pipeline.job --config "$EXPORT_CONFIG" --log gltf-export.log -- \
  blender --background --factory-startup --disable-autoexec --python-exit-code 1 \
  -P blender/export_gltf.py -- \
  --source "$SOURCE_BLEND" --output "$EXPORT_STAGING" --recipe "$EXPORT_CONFIG"
```

Require `export-receipt.json` with `complete: true` and matching source hashes in
addition to subprocess success. Raw GLBs, manifests, textures, and receipts are
diagnostic staging outputs, not permission to publish. The exporter never saves
the opened Blender source. Do not serve the repository or an export directory:
browser checks use a curated public-only tree beneath `/street-scene-showcase/`.

The initial 1024-pixel carbon atlas lost detail in close-up fixtures; the current
candidate recipe uses 2048 pixels and records its deterministic UV-layout hash.
The example retains the starting resolution. Asymmetric six-axis material crops
verify UV phase/orientation; periodic signed-normal checks and matched material
crops cover bump conversion. The baked weave remains a finite-resolution
approximation, not procedural or Cycles parity.

Run the independent actual-scene inspection under the same fresh supervisor:

```sh
python3 -m pipeline.job --config "$EXPORT_CONFIG" --log inspect-export.log -- \
  blender --background --factory-startup --disable-autoexec --python-exit-code 1 \
  -P tests/inspect_gltf_export.py -- \
  --source "$SOURCE_BLEND" --glb "$RAW_GLB" --receipt "$INSPECTION_RECEIPT"
```

Require its complete receipt. Small material fixtures use the same script with
`--material-crops "$FIXTURE_DIRECTORY"`; `--fixture` runs signed-UV/normal checks.

## References and rights

See [CREDITS.md](CREDITS.md) for material sources and external reference links.
The supplied Manhattan video is a visual reference, not a bundled production asset.
The selected reference interval is 6.25 through 11.25 seconds.
Its source frames are 150 through 269.
