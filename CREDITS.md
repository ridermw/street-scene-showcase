# References and material sources

## Concept and visual reference

No separate drawn concept art was created.
The [concept page](https://ridermw.github.io/street-scene-showcase/concept.html)
shows early scene studies and explains the visual direction.

- [Original Manhattan reference video](https://somethingbig.ai/post-assets/astra-review/new-york-manhattan.mp4)
- [3D Worlds guide](https://somethingbig.ai/3d-worlds)
- [Gauntlet Loop article](https://somethingbig.ai/gauntlet-loop)
- [Related model review and scene context](https://somethingbig.ai/astra-review)

The reference interval is 6.25 through 11.25 seconds at 24 fps.
The public site links to the original video. It does not host reference frames or clips.
Links do not grant redistribution rights.

## Scene materials

Vehicle and building geometry is original procedural work.
No external vehicle models or brand marks were used.

| Material | Source | Terms |
|---|---|---|
| Brick surfaces | [ambientCG Bricks059](https://ambientcg.com/a/Bricks059) | CC0 1.0 |
| Asphalt surface | [ambientCG Asphalt012](https://ambientcg.com/a/Asphalt012) | CC0 1.0 |

[ambientCG license information](https://docs.ambientcg.com/license/)
and [CC0 1.0 terms](https://creativecommons.org/publicdomain/zero/1.0/).

Color, roughness, and displacement images were used.
Brick scale is 1.05 meters. Asphalt scale is an inferred 1.5 meters.
The displayed renders and final video come from this scene.

## Interactive conversion and comparisons

The export code derives tangent-space normal maps from the retained CC0 height
images and converts world-space brick/asphalt projection to tiled UV coordinates.
It bakes only the original procedural carbon base color. The initial atlas was
1024 by 1024; the current candidate uses 2048 by 2048 to retain more weave detail.
These conversions approximate source bump filtering and procedural detail; their
appearance was approved for publication with the documented limitations on
September 10, 2026.

Lossless PNG storage conversion is implemented separately from material
conversion. It preserves image dimensions and decoded RGBA pixels, using exact
palette indices where possible and retaining standard color-space metadata. Descriptive
image metadata is omitted. Original JPEG texture bytes are not recompressed.
The complete compressed package passes technical validation and includes the
Three.js and meshoptimizer MIT license texts.

The seven text objects are converted to geometry from Blender's built-in Bfont:
one fictional `MARKET` sign and six fictional `SCN 018` plates. No font files are
distributed. Vehicle and building geometry remains original procedural work.

The viewer uses Three.js and its bundled Meshopt decoder. Their full license
notices are included in `docs/assets/interactive/THIRD_PARTY_NOTICES.txt`.
The sky/ground lighting environment is generated procedurally in the viewer;
no external HDRI or reference imagery is distributed.
The frozen candidate has passed the technical browser and desktop performance
gates. The public side-by-side page includes the same approved labeled Blender
renders, interactive captures and full browser motion recording. These are images
of the original procedural scene, not frames from the external reference video.
Private paths, source records, intermediate diagnostics and review logs are excluded.
Absent indirect/contact lighting, different reflections and paint highlights,
flat sky/contrast, and shadow aliasing/coverage remain visible differences accepted
for this interpretation. The public GLB embeds the derived texture package.
No external reference frames, reference clips, font files or private source archive
are distributed.
