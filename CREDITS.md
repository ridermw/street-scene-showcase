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

## Interactive conversion (in development)

The export code derives tangent-space normal maps from the retained CC0 height
images and converts world-space brick/asphalt projection to tiled UV coordinates.
It bakes only the original procedural carbon base color into a 1024 by 1024 atlas.
These conversions approximate source bump filtering and procedural detail; their
appearance has not been approved for publication.

The seven text objects are converted to geometry from Blender's built-in Bfont:
one fictional `MARKET` sign and six fictional `SCN 018` plates. No font files are
distributed. Vehicle and building geometry remains original procedural work.

The developing viewer uses Three.js and its bundled Meshopt decoder. A complete
release must include their applicable license notices with the approved bundle.
No interactive model, derived texture package, or reference comparison media has
been published yet.
