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
The initial browser proof loads beneath the production site prefix and captures
exact 1920 by 1080 frames. It is not a release candidate: shaded surfaces are too
bright, reflections differ substantially, and shadows require calibration.
The initial browser used software rendering, so it establishes no hardware
performance result. Lossless asset preparation, playback and inspection controls,
failure-path coverage, final visual
approval, and publication remain outstanding.

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
