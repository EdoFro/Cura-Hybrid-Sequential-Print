# Future ideas and roadmap

> Language: English. [Read this roadmap in Spanish](roadmap.md).

This document records possible improvements. Nothing in this list should be
interpreted as available functionality. Every change that expands the
compatibility envelope must preserve the *fail-closed* principle, include
automated tests, and first pass static G-code review.

## Table of contents

- [Suggested priority](#suggested-priority)
  - [Next diagnostic improvements](#next-diagnostic-improvements)
  - [Print-order policies](#print-order-policies)
  - [Collision detection](#collision-detection)
- [Safety and compatibility improvements](#safety-and-compatibility-improvements)
  - [Explicit modal parser](#explicit-modal-parser)
  - [More complete profile validation](#more-complete-profile-validation)
  - [Absolute extrusion support](#absolute-extrusion-support-p1--high-priority)
  - [Normal supports](#normal-supports-p2--medium-priority)
  - [Tree supports](#tree-supports-p3--low-priority)
  - [Raft and adhesion structures](#raft-and-adhesion-structures-p2--medium-priority)
  - [Multi-stage sequential printing](#multi-stage-sequential-printing)
  - [Automatic detection of thermal stages](#automatic-detection-of-thermal-stages)
  - [Optional filament-change pause](#optional-filament-change-pause-between-stages)
  - [Transitions and parking](#configurable-transitions-and-parking-area)
  - [Extended thermal control](#extended-thermal-control)
    - [Heated chamber](#heated-chamber-p3--low-priority)
- [Quality and tests](#quality-and-tests)
- [User experience](#user-experience)
- [Ideas from physical tests](#ideas-recorded-from-physical-tests)

## Summary table

| Area | Main proposals | Suggested priority | General status |
|---|---|---|---|
| Diagnostics and auditing | Last-run log, CLI validator, and embedded summary | High | Pending |
| Print ordering | Order by height, position, distance, or manual selection | Medium | Pending |
| Physical safety | Collision detection and a safe parking area | High | Research required |
| G-code compatibility | Modal parser and extended profile validation | High | Pending |
| Extrusion mode | Safe absolute-extrusion (`M82`) support | High | Pending |
| Normal supports | Validate object-local support structures | Medium | Pending |
| Tree supports | Analyze geometry and lateral variation by layer | Low | Pending |
| Complex adhesion | Raft and its relationship to previous/shared layers | Medium | Pending |
| Staged printing | Multiple configurable boundaries and automatic thermal detection | Medium | Proposed design |
| Filament changes | Pause, beep, parking, and safe resumption | Medium | Proposed design |
| Thermal control | More commands, tools, and a conservative mode | Medium | Partially implemented |
| Quality | Real fixtures, fuzzing, semantic comparator, and compatibility matrix | High | In progress |
| User experience | Validation, messages, preview, and checklist | Medium | Pending |

## Suggested priority

### Next diagnostic improvements

#### Last-run report

Generate an audit file that is overwritten on each run, with no accumulated
history. At minimum, it should record:

- script and Cura versions;
- relevant profile and parameter values;
- number of detected chunks, objects, and layers;
- detected XYZ/E modes and their transitions;
- maximum heights, clearance, and XYZ resume points;
- detected inter-object preludes;
- retained or omitted thermal waits and the reason;
- original and resulting order;
- `APPLIED` or `REJECTED`, including the validation that decided rejection;
- input and output G-code hashes to identify exactly what was audited.

The log should not contain the complete G-code or unnecessary paths. Before
implementation, a stable writable location inside Cura's configuration must be
confirmed. A more portable alternative would be a short report embedded as
G-code comments, with an external log offered only as an option.

**Acceptance criterion:** a new run atomically replaces the previous report; a
failure to write the log must not create partially transformed G-code or hide
the actual result.

#### Independent command-line validator

Create a small tool that accepts the original and transformed G-code without
requiring Cura and produces an audit report. It could check layer order, path
preservation, modal states, temperatures, XYZ limits, and added/removed content.

**Value:** easier review of real files, automated regression checks, and a
reproducible report for issue submissions.

#### Embedded audit summary

Add readable header comments such as object count, ordering policy, calculated
transitions, omitted thermal waits, and transformer version. This remains useful
when an external log is unavailable.

### Print-order policies

Allow users to choose how objects are completed after the common layers:

- original Cura order;
- shortest to tallest;
- tallest to shortest;
- left to right or right to left;
- front to back or back to front;
- shortest distance from a starting position;
- manually specified order.

Correct implementation will require identifying each object without relying
only on `;MESH:`, calculating a reliable bounding box, and moving every prelude
and associated state together with its object.

**Acceptance criterion:** the policy is deterministic, appears in the audit,
and preserves every path belonging to each object exactly. If two objects cannot
be identified unambiguously, retain the original order or reject transformation.

### Collision detection

Investigate geometric checking of the print head, carriage, and X gantry against
already completed parts. Possible approaches:

1. **Integration with Cura geometry before export.** Use print-head exclusion
   volumes and original object positions.
2. **External validator.** Simulate the full carriage volume—not only the
   nozzle—against meshes or object bounding boxes.
3. **Integration with an existing simulator.** Export G-code and machine
   geometry to a tool capable of reporting intersections.
4. **Conservative volume approximation.** Use oversized boxes or cylinders when
   an exact carriage mesh is unavailable.

A postprocessor that receives only G-code does not always have the meshes or
complete carriage geometry. A strong solution will likely require a pre-G-code
Cura plugin or a second external tool.

**Acceptance criterion:** check every movement after each object is completed,
include configurable tolerances, and reject missing or ambiguous geometry. A
positive result reduces risk but must not be presented as an absolute guarantee
of physical safety.

## Safety and compatibility improvements

### Explicit modal parser

Gradually replace independent searches with a reduced G-code state interpreter:
`G90/G91`, `M82/M83`, XYZ/E, active tool, temperatures, fan, acceleration, and
units. The parser would accept only documented commands and formats; any
relevant unknown construction would cause rejection.

### More complete profile validation

- confirm one extruder and no `Tn` changes;
- check X/Y limits in addition to Z height;
- validate Marlin flavor from profile and header;
- record declared print-head dimensions and geometry;
- detect prime tower, ooze shield, draft shield, and shared structures;
- verify that effective settings match those encoded in the `SETTING_3` comment
  when available.

### Absolute extrusion support (P1 / high priority)

Allow G-code using absolute extrusion (`M82`) without changing the amount of
filament extruded when layers are reordered. Before resuming each object, the
script must restore the E value expected by that block through a validated
sequence, for example `G90`, `M82`, and `G92 E...`, according to the compatible
firmware.

Implementation must reconstruct modal E state at the end of every common layer,
including `G0`/`G1`/`G2`/`G3` moves, retractions, and `G92 E...` resets. It must
reject ambiguous transitions between `M82` and `M83`, multiple extruders, tools,
or unsupported E formats. It must also verify the effect of `G90` on extrusion
mode for every supported firmware.

**Acceptance criterion:** every resumption restores the E value expected by the
original G-code; fixtures cover extrusion, retractions, E resets, and arcs; and
supervised physical tests on an approved printer confirm no over-extrusion,
under-extrusion, or unexpected retractions.

### Normal supports (P2 / medium priority)

Investigate whether Cura normal supports remain unambiguously within each
object's block in `One at a Time` G-code. The analysis must verify that every
support path, interface, and support roof/floor belongs to one object and moves
with it, without creating travels that cross already completed parts.

**Acceptance criterion:** real fixtures with normal supports preserve every
path exactly once, layers and preludes remain unambiguous, and supervised
physical tests confirm correct printing. Until then, `support_enable` must
continue to be rejected.

### Tree supports (P3 / low priority)

Evaluate tree supports separately. Their branches can vary laterally between
layers and approach other objects, so their safety cannot be inferred from
normal supports. Research must include each branch's effective geometry and the
print head's collision constraints.

**Acceptance criterion:** conservative validation demonstrates that no branch
or print-head transition crosses an incompatible part or support; fixtures and
physical tests cover multi-object cases. Until then, tree supports remain
rejected.

### Raft and adhesion structures (P2 / medium priority)

Investigate raft support as a feature separate from supports. A raft can add
negative layers and shared structures before `;LAYER:0`, which do not belong
unambiguously to one object or to the current common phase. Brim remains out of
scope until equivalent validation of its paths exists.

**Acceptance criterion:** the analysis distinguishes raft from each object's
layers, preserves every path and thermal/modal state, and supervised physical
tests validate adhesion and transitions. Until then, raft and brim remain
rejected.

### Multi-stage sequential printing

Allow users to configure several layers where a new stage begins. For example,
with objects `A` and `B` and transitions at printed layers 3, 8, and 16, the
order would be:

```text
A1..2, B1..2,
A3..7, B3..7,
A8..15, B8..15,
A16..end, B16..end
```

The interface should use human numbering beginning at 1 and convert internally
to Cura numbering, which begins at `;LAYER:0`. It must also normalize the list,
reject duplicate or out-of-range numbers, and explain the resulting ranges
before transforming the file.

Every object switch between ranges requires a safe transition, modal-state
restoration, and validation of available layers. Collision checks must consider
the height already reached by every object, not only fully completed parts.

**Acceptance criterion:** every original path appears exactly once, stage
boundaries match the requested layers, and the resulting order is recorded in
the audit. Ambiguous or incompatible configurations are rejected without
modifying the G-code.

### Automatic detection of thermal stages

Analyze bed and extruder temperature targets to propose layers where a new stage
should begin. For example, if printed layers 1 and 2 use 230 °C and layer 3 onward
uses 225 °C, the script would propose layer 3 as the boundary and, with two
objects, conceptually produce:

```text
A1..2, B1..2, A3..end, B3..end
```

Detection must not mechanically interpret the location of an `M104` or `M140`:
Cura may issue a change at the end of the previous layer to anticipate heating
or cooling. The script must infer which layer the new target is intended for and
distinguish a real transition from an anticipated command, a wait, an
oscillation, or an incidental adjustment.

The analysis should:

- treat the bed and each compatible extruder separately;
- compare the thermal pattern of every object;
- require equivalent boundaries and consistent targets across objects;
- support detection of multiple thermal boundaries;
- display proposed layers before transformation;
- allow the user to accept, modify, or ignore the proposal;
- record which commands and layers led to each decision.

If objects contain different patterns, ambiguous commands, or oscillations that
cannot safely be attributed to a layer, automatic mode must reject the proposal
without modifying the G-code. Users could still configure stages manually using
the preceding feature.

**Acceptance criterion:** for every proposed boundary, the report identifies
the previous temperature, new temperature, printed layer to which the change is
attributed, and equivalent evidence in all objects. Output is not transformed
until the selection is explicitly confirmed.

### Optional filament-change pause between stages

Allow insertion of a pause with an audible alert between two stages, especially
between the initial common stage and sequential object completion. The sequence
could include:

- controlled retraction;
- lift and parking in a validated safe area;
- an audible `M300` alert when supported by the firmware;
- a firmware-compatible pause command, such as `M0` or `M25`;
- restoration of temperature, position, XYZ mode, extrusion mode, and retracted
  amount before resuming.

The pause should be optional at each stage boundary, allowing multiple heights
to produce several color changes. Implementation depends on the firmware and
printing method (SD card, USB, or OctoPrint), because pause commands do not
behave identically in every environment.

**Acceptance criterion:** the printer parks without crossing parts, filament
change does not alter subsequent coordinates or extrusion, and the file clearly
identifies the chosen pause command and its expected compatibility.

### Configurable transitions and parking area

Allow a validated waiting/purging position outside the parts when a thermal wait
is genuinely necessary. It could include retraction, parking, recovery, and a
wiping path, but only with a demonstrably clear area and verified machine limits.

### Extended thermal control

- safely recognize `R` parameters, `Tn` tools, and multiple extruders;
- explain in the audit why each wait was retained or removed;
- offer a conservative mode that never removes waits;
- use tests to confirm active targets do not change during reordering.

#### Heated chamber (P3 / low priority)

Implement validated support for `M141` and `M191`, which set and wait for a
heated-chamber temperature in compatible firmware. The current experimental
override allows continuation only after explicit consent, but does not prove
that reordering preserves the original thermal strategy.

The work must reconstruct chamber target and confirmation as an independent
thermal channel, define conservative handling for temperature changes between
objects, and validate the result with real G-code and supervised physical tests
on an approved printer.

**Acceptance criterion:** `M191` waits are omitted only when the exact chamber
target is already confirmed; ambiguous or incompatible changes are rejected
without modifying G-code; and a compatibility matrix records the printer,
firmware, profile, and tests performed.

## Quality and tests

### Anonymized real fixtures

Keep small real G-code files from compatible Cura versions, reduced and free of
private information, together with expected results. Large files can be
represented by structural excerpts or hashes to avoid repository bloat.

### Generative tests and fuzzing

Generate combinations of chunks, comments, whitespace, modes, and malformed
numbering. The primary property would be that inputs outside the validated
format never produce an applied transformation.

### Semantic comparator

Automatically verify that every original path appears exactly once in output,
belongs to the same object, and changes position only as an authorized block.
It should also verify the modal state active for every extrusion movement.

### Compatibility matrix

Record which Cura versions, firmware, printers, materials, and profiles received
only static tests and which received supervised physical runs. Do not generalize
an Ender 3 Pro result to other machines.

## User experience

- show a precise explanation for every Cura rejection and how to correct it;
- add a validate-only mode that does not reorder;
- generate recognizable names/versions in file comments;
- warn when the same G-code was already processed;
- provide a preview of object order and transitions;
- provide a checklist before a supervised physical test.

## Ideas recorded from physical tests

- **Resolved:** restore `M83` after the inserted `G90`.
- **Resolved:** distinguish a real thermal change from a repetition of the
  current target, such as `M104 S220` when the hotend is already requested at
  220 °C. The repetition is retained and does not require an equivalent command
  in every common layer.
- **Implemented and physically validated in the tested configuration:** defer
  the normal-temperature `M104` until the final common layer and omit
  `M109`/`M190` only when the exact target is currently requested and confirmed
  without intervening changes. A supervised 16-object print successfully
  completed the common phase and sequential object completion.
- **Pending:** reduce ooze risk when a thermal wait is genuinely necessary by
  using a validated parking area.
- **Pending:** collect the result, photographs, and exact firmware of each test
  without storing private information by default.
