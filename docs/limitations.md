# Limitations and risks

- Safe nozzle Z does not prove the whole Ender 3 Pro carriage clears a tall object. Cura's One-at-a-Time placement check and generous spacing remain mandatory.
- Travel can scar or detach the first layers already on the bed.
- Reordering changes cooling, elapsed time, and fan/temperature state assumptions; time estimates are not rewritten.
- `;LAYER:` is validated strictly, but comments are not a formal interchange schema.
- Shared adhesion/support structures are unsafe. Prefer adhesion None; supports are rejected.
- Only `M83` relative extrusion is accepted. Absolute E recalculation is not implemented.
- Every common-layer chunk must establish a complete absolute XYZ position. The transition restores its final XYZ state because Cura 5.12 can begin the following layer with immediate extrusion and no entry travel.
- v0.3 preserves Cura's object order and supports only the documented Ender 3 Pro/Marlin envelope.

An emergency stop and physical supervision are part of the procedure, not optional collision protection.
