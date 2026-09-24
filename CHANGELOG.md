# Changelog

All notable changes follow Keep a Changelog; versions follow Semantic Versioning.

## [Unreleased]

## [0.2.0] - 2026-09-24

### Added

- Track requested and confirmed bed/hotend targets so redundant inter-object
  waits can be identified conservatively.
- Add paired original/transformed four-object G-code examples from a successful
  supervised physical print.
- Expose the release version in Cura's script name and settings description.

### Changed

- Raise the preventive object-count limit from four to 50, with successful test
  coverage for 5, 10, 20, and 50 objects and rejection of 51 or more.
- Keep the normal-temperature `M104` at first-layer temperature until the final
  common layer while preserving Cura's thermal lead time.
- Use English comments and docstrings in the public source code.

### Fixed

- Restore `M83` immediately after each transition's `G90`; on Marlin, `G90` clears the relative-extrusion override and otherwise prevents normal relative-E delivery after the common layer.
- Skip an inter-object `M109`/`M190` wait only when its exact target is both currently requested and already confirmed; preserve changed or uncertain waits.
- Invalidate thermal confirmation when `M104`/`M140` changes a target, including change-away-then-return sequences.
- Distinguish actual common-layer hotend target changes from unchanged `M104`
  repetitions, allowing profiles whose initial and normal temperatures are
  equal while retaining fail-closed rejection for inconsistent real changes.
- Reject negative pre-object layers.
- Restore each common layer's final XYZ state before resuming its object; Cura 5.12 may start layer 1 with immediate extrusion and no entry travel.
- Associate CuraEngine's trailing unnumbered inter-object message with the following `LAYER:0`, while continuing to reject unnumbered messages embedded between numbered layers.
- Recognize indented/lowercase positioning-mode commands and reject XYZ coordinate resets.
- Track ordered extrusion modes so a Start G-code `M82` is accepted only when a later `M83` makes relative extrusion active before the first layer.
- Permit conventional `G91`/`G90` and `M82` commands inside a detached ending block or after Cura's final `;TIME_ELAPSED:` boundary while continuing to reject them in transformed regions.
- Validate clearance and machine dimensions as finite, positive values.

### Tests

- Add regression coverage for the stricter structural, command, entry-motion, and numeric validation.
- Record a successful supervised physical test of the transformed 16-object
  `BodyBox x16 hybrid.gcode`, including the common first-layer phase, all safe
  transitions, sequential completion, extrusion, and thermal behavior.

### Documentation

- Add synchronized English and Spanish diagram-based code guides for developers
  coming from Groovy, VBA, Java, VB, or C#.
- Record the successful physical two-object test and the Marlin `G90`/`M83` lesson.
- Add synchronized English and Spanish roadmaps covering last-run audit logs,
  ordering policies, collision detection, parser hardening, compatibility, and
  future tests.

## [0.1.0] - 2026-09-04

### Added

- Conservative Cura 5.12.0 post-processing script.
- One shared first layer followed by object-at-a-time completion.
- Fail-closed structural, profile, extrusion-mode, and Z-height validation.
- Safe transition moves and duplicate-run protection.
- Unit tests, two-cube fixture, documentation, MIT license, and CI workflow.
