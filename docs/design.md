# Design notes

## Cura 5.12 conventions checked

The 5.12.0 `Script` base class defines `getSettingDataString()` and `execute(data: List[str]) -> List[str]`. The Post Processing plugin loads a module whose class has the same name, initializes it, runs scripts in order, and adds `;POSTPROCESSED`. This project therefore ships one same-named module/class and uses Cura's version-2 settings JSON. Profile values come from the global container stack, as in bundled scripts.

Primary sources:

- <https://github.com/Ultimaker/Cura/blob/5.12.0/plugins/PostProcessingPlugin/Script.py>
- <https://github.com/Ultimaker/Cura/blob/5.12.0/plugins/PostProcessingPlugin/PostProcessingPlugin.py>
- <https://github.com/Ultimaker/Cura/tree/5.12.0/plugins/PostProcessingPlugin/scripts>
- <https://github.com/Ultimaker/Cura/releases/tag/5.12.0>

## Transformation

Input order is `A0,A1,...,An,B0,B1,...,Bn`; output is `A0,B0,A1,...,An,B1,...,Bn`. The script relies on repeated monotonic `;LAYER:` runs from a one-at-a-time slice, not `;MESH:` comments.

CuraEngine may emit an unnumbered inter-object prelude containing retraction, clearance travel, heating commands, and the next `;LAYER_COUNT`. A trailing unnumbered block immediately before the next `;LAYER:0` is attached to that next object's common layer and moves with it. Unnumbered blocks embedded between numbered layers remain ambiguous and are rejected.

Relative E makes extrusion values local increments. XYZ stays absolute. Before each object resumes at layer 1, Z rises above the previously completed height, XY moves above the final position recorded from that object's common layer, and Z returns to that recorded height. Restoring the common-layer endpoint is necessary because Cura 5.12 can start layer 1 by extruding immediately from the preceding layer's modal XYZ position.

Marlin's `G90` also clears the `M83` extrusion override. Every generated transition therefore emits `G90` followed by `M83` before moving, preserving absolute XYZ and relative E simultaneously.

Extrusion and XYZ mode checks apply to the header and layer runs that participate in the transformation. Cura's ending block—either detached or embedded after the final `;TIME_ELAPSED:` marker—is preserved byte-for-byte and may contain its conventional temporary `G91`/`G90` sequence and final `M82`. Commands before that validated boundary remain subject to the strict mode checks.

Header extrusion commands are evaluated in order. A profile's Start G-code may issue `M82`, but `M83` must be the final extrusion mode before the first layer and no layer may switch back to `M82`.

## Redundant thermal waits

The transformer keeps separate `requested` and `confirmed` targets for the bed and hotend. Non-blocking `M140`/`M104` update the requested target and invalidate a different confirmed target; retained blocking `M190`/`M109` establish a confirmed target. Returning later to an older value does not restore its confirmation. In an inter-object preamble, a blocking wait is replaced by `HYBRID_SEQUENCE:SKIPPED_REDUNDANT_...` only when its `S` value exactly matches both current states without an intervening change. A changed target, an unsupported parameter form, or missing prior confirmation preserves the original command.

For a hybrid common-layer phase, Cura's early `M104` transition to the normal
printing temperature must also be rescheduled. The transformer reconstructs the
requested target through the header, inter-object preludes, and common layers so
an unchanged repetition such as `220 -> 220` is not mistaken for a transition.
If every common layer contains exactly one identical actual target change, the
transformer replaces it with `HYBRID_SEQUENCE:DEFERRED_COMMON_M104` in every
common layer except the last. The last command remains at its original position,
so Cura's intentional thermal anticipation occurs near the end of the overall
common-layer phase. If there are no actual changes, commands are retained. A
missing, multiple, or different actual transition causes rejection rather than
inference.

Post-processing cannot recompute combing, collision envelopes, cooling, estimates, or acceleration paths. Unrecognized structure returns the original list with a `REJECTED` comment.
