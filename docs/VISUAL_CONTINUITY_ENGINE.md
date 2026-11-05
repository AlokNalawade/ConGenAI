# Visual Continuity Engine

## Purpose
ConGenAI's visual pipeline needs more than a style prompt. The engine carries
stable visual constraints across shots so the selected image/video provider can
be instructed to preserve character identity, locations, props, chronology,
screen direction, physical action and cinematic language.

## Concepts
- **Visual Bible**: project-level style, character anchors, environment anchors,
  persistent props and global constraints.
- **Scene continuity state**: chronology, character positions, action state,
  prop state, screen direction, camera setup and transitions.
- **Prompt compiler**: combines the scene's creative description with the Visual
  Bible and physicality/cinematography/continuity rules.
- **Evaluator (next phase)**: compare generated frames against references and
  adjacent scenes; detect identity drift, layout changes, temporal jumps and
  implausible motion. Prompting alone cannot guarantee model compliance.

## First implementation boundary
The current renderer creates still images and combines them with narration. This
foundation improves consistency instructions but does not create true character
animation, simulate physics, or perform visual similarity checks. Those require
reference-image capable generation providers, a temporal video model, and/or
Blender scene assets. Do not label a clip as physics-validated until an evaluator
has inspected it.

## Planned increments
1. Persist a Visual Bible and per-scene continuity state against each pipeline run.
2. Generate canonical character/location/prop reference sheets.
3. Route reference images and continuity prompts to providers that support them.
4. Add frame extraction and automated identity/layout/motion QA with retry gates.
5. Add Blender for repeatable sets, camera paths and deterministic physical
   simulation where it is more reliable than generative video.
6. Add director profiles (documentary, epic, thriller, action, emotional drama)
   as cinematography presets, not as replacements for continuity constraints.
