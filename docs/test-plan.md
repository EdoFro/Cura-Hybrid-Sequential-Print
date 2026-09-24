# Test plan: two 20 mm cubes

Create two separate 20 × 20 × 20 mm cubes, far apart left-to-right and inside Cura's valid One-at-a-Time zones. Use an Ender 3 Pro profile, one 0.4 mm nozzle, PLA, no supports, adhesion None, **Print Sequence > One at a Time**, and **Relative Extrusion**.

## Static checks

1. Save an unmodified export, then enable the script, re-slice, and save the transformed export.
2. Confirm one `APPLIED`, two `;LAYER:0` before the first `;LAYER:1`, and two safe-transition markers.
3. Confirm `M83` is active for printing, `M82`/`G91` are absent from transformed layer regions, and every inserted transition contains `G90` immediately followed by `M83`.
4. In an independent viewer confirm: cube A layer 0, cube B layer 0, remaining A, remaining B.
5. Inspect transitions: Z rises, XY moves above the target, then Z descends; all Z values fit the profile height.
6. Compare start/end and heater commands with the unmodified export.

## Hardware stages

1. If your workflow permits it safely, dry-run without filament and with heaters disabled; keep emergency stop/power within reach.
2. Print two 5 mm-tall cubes first at reduced speed.
3. Then print the 20 mm cubes while supervising every transition.
4. Record Cura project, both G-code files, firmware, placement, video, and result.

## Rejection tests

Confirm the original is retained and marked `REJECTED` for All at Once, M82, G91, XYZ `G92`, supports, brim/raft, one or more than 50 objects, negative/malformed numbering, an incomplete common-layer XYZ endpoint, invalid clearance, or insufficient Z height. Confirm successful static transformations with 5, 10, 20 and 50 synthetic objects; treat the ceiling of 50 as a preventive resource guard rather than an algorithmic restriction.

## Recorded physical results

- A supervised print of two small 12 × 12 × 4 mm objects completed successfully
  after restoring `M83` immediately after every inserted `G90`.
- A supervised `BodyBox x16 hybrid.gcode` print completed successfully: all 16
  first layers printed before sequential completion of the 16 objects, with the
  expected extrusion and thermal behavior.

These results apply only to the files and Ender 3 Pro/Cura 5.12.0 configuration
that were tested. They do not establish collision safety for another placement,
geometry, profile, firmware, or printer.
