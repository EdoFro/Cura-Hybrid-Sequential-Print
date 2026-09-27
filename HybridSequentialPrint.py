# Copyright (c) 2026 EdoFro
# SPDX-License-Identifier: MIT
"""Conservative Cura post-processing script for experimental hybrid sequencing.

The input MUST already be sliced "One at a Time".  CuraEngine then emits a new
``;LAYER:0`` run for every object.  This script moves the first chunk of every
run to the front and keeps the remaining chunks object-by-object.  It refuses
to edit G-code unless all structural and printer-profile checks pass.
"""

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

# These classes exist inside Cura. Unit tests provide minimal stubs so the pure
# transformation logic can be tested without opening Cura.
from ..Script import Script
from UM.Application import Application
from UM.Logger import Logger
from UM.Message import Message


# Precompiled regular expressions are roughly equivalent to creating one
# Pattern instance in Java/Groovy and reusing it for every search.
LAYER_RE = re.compile(r"(?m)^;LAYER:(-?\d+)\s*$")
MOVE_RE = re.compile(r"^\s*(G0|G1|G2|G3)(?=\s|$)", re.IGNORECASE)
ARC_RE = re.compile(r"^\s*(G2|G3)(?=\s|$)", re.IGNORECASE)
NON_XY_ARC_PLANE_RE = re.compile(r"^\s*(G18|G19)(?=\s|$)", re.IGNORECASE)
AXIS_RE = re.compile(r"(?:^|\s)([XYZ])(-?(?:\d+(?:\.\d*)?|\.\d+))(?=\s|;|$)", re.IGNORECASE)
TEMP_COMMAND_RE = re.compile(r"^\s*(M104|M109|M140|M190)(?=\s|;|$)", re.IGNORECASE)
CHAMBER_COMMAND_RE = re.compile(r"^\s*(M141|M191)(?=\s|;|$)", re.IGNORECASE)
S_PARAM_RE = re.compile(r"(?:^|\s)S(-?(?:\d+(?:\.\d*)?|\.\d+))(?=\s|;|$)", re.IGNORECASE)
SCRIPT_VERSION = "0.3.0"
# Preventive limit, not an algorithmic restriction. It stops a malformed file
# containing thousands of false ``;LAYER:0`` starts from consuming excessive
# resources inside Cura. It can be reviewed after larger real-world tests.
MAX_OBJECTS = 50

# Profiles in this list have been validated by the project. Keep it restricted
# to printer/profile combinations that have passed G-code review and supervised
# physical tests.
APPROVED_MACHINE_NAMES = ("Ender 3 Pro",)
# Add a local profile name here only for supervised experimental tests. Before
# promoting a profile to APPROVED_MACHINE_NAMES, review its generated G-code,
# verify its firmware commands and motion limits, and run simple two-object
# prints under supervision. A successful test does not validate other firmware,
# start/end G-code, nozzle, or accessory configurations of the same model.
TEST_MACHINE_NAMES: Tuple[str, ...] = ()


class ValidationError(ValueError):
    """Raised when changing the supplied G-code would be unsafe or ambiguous."""


@dataclass
class ObjectRuns:
    """The G-code regions around the sequential per-object layer runs."""

    prefix: List[str]
    runs: List[List[str]]
    suffix: List[str]


def _machine_name_key(name: str) -> str:
    """Normalize harmless spelling differences in a Cura machine name."""
    return re.sub(r"[\s_-]+", "", name).casefold()


def _machine_tier(machine_name: str) -> Optional[str]:
    """Return the validation tier for a configured machine name, if any."""
    key = _machine_name_key(machine_name)
    if any(key == _machine_name_key(name) for name in APPROVED_MACHINE_NAMES):
        return "approved"
    if any(key == _machine_name_key(name) for name in TEST_MACHINE_NAMES):
        return "test"
    return None


def _setting_float(value: Any, setting_name: str) -> float:
    """Convert a Cura setting while making malformed values a safe rejection."""
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValidationError("{} must be numeric".format(setting_name))


def _layer_number(chunk: str) -> Optional[int]:
    """Return the chunk's single layer number, or None when it has none."""
    matches = LAYER_RE.findall(chunk)
    if not matches:
        return None
    if len(matches) != 1:
        raise ValidationError("a G-code block contains more than one ;LAYER marker")
    return int(matches[0])


def _split_object_runs(data: Sequence[str]) -> ObjectRuns:
    """Split Cura's list into a header, sequential objects, and an ending.

    Each object is itself a list of chunks, one per numbered layer.
    """
    # A Python list comprehension builds (index, layer) pairs.
    numbered = [(index, _layer_number(chunk)) for index, chunk in enumerate(data)]
    starts = [index for index, number in numbered if number == 0]
    if len(starts) < 2:
        raise ValidationError("fewer than two unambiguous ;LAYER:0 object runs were found")
    if len(starts) > MAX_OBJECTS:
        raise ValidationError("more than {} objects exceed the preventive safety limit".format(MAX_OBJECTS))
    if any(number is not None for _, number in numbered[:starts[0]]):
        raise ValidationError("layer markers, including negative layers, appeared before the first object")

    prefix = list(data[:starts[0]])
    runs: List[List[str]] = []
    suffix: List[str] = []
    # CuraEngine may emit an unnumbered chunk between two objects. It contains
    # the next object's safe travel and heating commands, so it must move with
    # that object's LAYER:0 rather than remain at the end of the previous one.
    pending_prelude: List[str] = []
    for position, start in enumerate(starts):
        stop = starts[position + 1] if position + 1 < len(starts) else len(data)
        run = list(data[start:stop])
        trailing: List[str] = []
        while run and _layer_number(run[-1]) is None:
            trailing.insert(0, run.pop())
        if pending_prelude:
            run[0] = "".join(pending_prelude) + run[0]
        if position == len(starts) - 1:
            suffix = trailing
            pending_prelude = []
        else:
            pending_prelude = trailing
        # After removing the trailing prelude, an unnumbered chunk between
        # numbered layers would be ambiguous, so the transformation is rejected.
        numbers = [_layer_number(chunk) for chunk in run]
        if not numbers or numbers[0] != 0 or any(number is None for number in numbers):
            raise ValidationError("non-layer data appeared inside an object run")
        ints = [int(number) for number in numbers if number is not None]
        if ints != list(range(0, len(ints))):
            raise ValidationError("layer numbers do not restart at 0 and increase by one per object")
        if len(run) < 2:
            raise ValidationError("every object must contain at least two layers")
        runs.append(run)
    return ObjectRuns(prefix=prefix, runs=runs, suffix=suffix)


def _max_z(chunks: Sequence[str]) -> float:
    """Find the greatest explicit Z in G0/G1 moves across several chunks."""
    values: List[float] = []
    for chunk in chunks:
        for line in chunk.splitlines():
            if MOVE_RE.match(line):
                values.extend(float(value) for axis, value in AXIS_RE.findall(line) if axis.upper() == "Z")
    if not values:
        raise ValidationError("could not determine object Z heights")
    return max(values)


def _end_point(chunk: str) -> Tuple[float, float, float]:
    """Reconstruct the absolute XYZ state at the end of a common layer."""
    # ``position`` behaves like a Map<String, Double>. Each new axis value
    # replaces the previous one, just like the printer's modal state.
    position: Dict[str, float] = {}
    for line in chunk.splitlines():
        if not MOVE_RE.match(line):
            continue
        for axis, value in AXIS_RE.findall(line):
            position[axis.upper()] = float(value)
    if set(position) != {"X", "Y", "Z"}:
        raise ValidationError("a common layer does not establish a complete XYZ end position")
    return position["X"], position["Y"], position["Z"]


def _validate_arc_moves(chunks: Sequence[str]) -> None:
    """Allow only planar XY arcs while preserving a reliable XYZ endpoint.

    Arc Welder normally emits G2/G3 arcs in the XY plane without a Z word.
    A helical arc or a non-XY arc plane needs more geometric validation than
    this script provides, so it must leave the G-code unchanged.
    """
    for chunk in chunks:
        for line in chunk.splitlines():
            if NON_XY_ARC_PLANE_RE.match(line):
                raise ValidationError("non-XY arc planes (G18/G19) are unsupported")
            if ARC_RE.match(line) and any(axis.upper() == "Z" for axis, _ in AXIS_RE.findall(line)):
                raise ValidationError("arcs with Z movement (G2/G3) are unsupported")


def _validate_chamber_commands(chunks: Sequence[str], allow_unvalidated: bool) -> bool:
    """Require explicit consent before reordering heated-chamber commands."""
    found = any(
        CHAMBER_COMMAND_RE.match(line)
        for chunk in chunks
        for line in chunk.splitlines()
    )
    if found and not allow_unvalidated:
        raise ValidationError(
            "heated-chamber commands (M141/M191) are unvalidated; enable the experimental setting only after review"
        )
    return found


def _insert_transition(chunk: str, safe_z: float, target: Tuple[float, float, float]) -> str:
    """Insert a transition before the resumed layer's content."""
    x, y, target_z = target
    marker = LAYER_RE.search(chunk)
    if marker is None:
        raise ValidationError("transition target has no layer marker")
    # On Marlin, G90 also affects the extruder. M83 must follow it to keep XYZ
    # absolute while E remains relative. Omitting it caused a physical test to
    # stop extruding after the common layers.
    insertion = (
        "\n;TYPE:CUSTOM\n"
        ";HYBRID_SEQUENCE:SAFE_TRANSITION\n"
        "G90 ; hybrid: absolute positioning\n"
        "M83 ; hybrid: restore relative extrusion after G90\n"
        "G0 Z{:.3f} ; hybrid: clear completed object\n"
        "G0 X{:.3f} Y{:.3f} ; hybrid: move above next object\n"
        "G0 Z{:.3f} ; hybrid: descend to target layer\n".format(safe_z, x, y, target_z)
    )
    return chunk[:marker.end()] + insertion + chunk[marker.end():]


def _process_thermal_commands(text: str, requested: Dict[str, float],
                              confirmed: Dict[str, float], remove_redundant: bool) -> str:
    """Track thermal targets and omit only waits that are already confirmed."""
    result: List[str] = []
    for line in text.splitlines(keepends=True):
        command_match = TEMP_COMMAND_RE.match(line)
        target_match = S_PARAM_RE.search(line)
        if command_match is None or target_match is None:
            result.append(line)
            continue

        command = command_match.group(1).upper()
        target = float(target_match.group(1))
        channel = "hotend" if command in ("M104", "M109") else "bed"
        if command in ("M104", "M140"):
            # A confirmation describes only the current target. If a
            # non-blocking command changes it, reaching an earlier temperature
            # does not prove that the new one has been reached. Returning to an
            # older value later still requires a new confirmation.
            if confirmed.get(channel) != target:
                confirmed.pop(channel, None)
            requested[channel] = target
            result.append(line)
            continue

        redundant = requested.get(channel) == target and confirmed.get(channel) == target
        if remove_redundant and redundant:
            newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            result.append(";HYBRID_SEQUENCE:SKIPPED_REDUNDANT_{} S{:g}{}".format(command, target, newline))
            continue

        # If the wait is retained, completion proves that the target was
        # reached. An S parameter in M109/M190 also sets the requested target.
        requested[channel] = target
        confirmed[channel] = target
        result.append(line)
    return "".join(result)


def _common_layer_m104_transitions(prefix: Sequence[str],
                                    common: Sequence[str]) -> List[List[float]]:
    """Return only M104 commands that actually change the hotend target.

    Cura may repeat the current target inside the first object's initial layer
    and put it in later objects' preludes. That pattern is not a thermal
    transition and must not require every layer to contain M104. Reconstructing
    state in order distinguishes ``220 -> 220`` from a real change such as
    ``230 -> 225``.
    """
    requested: Dict[str, float] = {}
    confirmed: Dict[str, float] = {}
    for chunk in prefix:
        _process_thermal_commands(chunk, requested, confirmed, False)

    transitions_by_object: List[List[float]] = []
    for chunk in common:
        marker = LAYER_RE.search(chunk)
        if marker is None:
            raise ValidationError("common layer has no layer marker")

        # The prelude belongs to the next object and may restore its first-layer
        # temperature before the LAYER:0 marker.
        _process_thermal_commands(chunk[:marker.start()], requested, confirmed, False)
        transitions: List[float] = []
        for line in chunk[marker.start():].splitlines(keepends=True):
            command_match = TEMP_COMMAND_RE.match(line)
            target_match = S_PARAM_RE.search(line)
            if (
                command_match is not None
                and command_match.group(1).upper() == "M104"
                and target_match is not None
            ):
                target = float(target_match.group(1))
                if requested.get("hotend") != target:
                    transitions.append(target)
            _process_thermal_commands(line, requested, confirmed, False)
        transitions_by_object.append(transitions)
    return transitions_by_object


def _replace_common_m104_with_audit_comment(chunk: str, target: float) -> str:
    """Replace one common-layer M104 without altering other lines."""
    marker = LAYER_RE.search(chunk)
    if marker is None:
        raise ValidationError("common layer has no layer marker")
    before = chunk[:marker.end()]
    after: List[str] = []
    replaced = 0
    for line in chunk[marker.end():].splitlines(keepends=True):
        command_match = TEMP_COMMAND_RE.match(line)
        target_match = S_PARAM_RE.search(line)
        is_target = (
            command_match is not None
            and command_match.group(1).upper() == "M104"
            and target_match is not None
            and float(target_match.group(1)) == target
        )
        if is_target:
            newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            after.append(";HYBRID_SEQUENCE:DEFERRED_COMMON_M104 S{:g}{}".format(target, newline))
            replaced += 1
        else:
            after.append(line)
    if replaced != 1:
        raise ValidationError("could not replace exactly one common-layer M104")
    return before + "".join(after)


def _defer_common_hotend_transition(prefix: Sequence[str],
                                     common: Sequence[str]) -> List[str]:
    """Keep the layer-0 temperature until the final common layer."""
    targets_by_object = _common_layer_m104_transitions(prefix, common)
    if all(not targets for targets in targets_by_object):
        return list(common)
    if any(len(targets) != 1 for targets in targets_by_object):
        raise ValidationError("every common layer must contain exactly one actual M104 temperature transition")
    targets = [values[0] for values in targets_by_object]
    if any(target != targets[0] for target in targets[1:]):
        raise ValidationError("common-layer M104 temperature targets differ between objects")

    # Early common layers remain at first-layer temperature. The final object's
    # M104 stays in its original position to preserve Cura's calculated thermal
    # lead time before LAYER:1 resumes.
    deferred = [
        _replace_common_m104_with_audit_comment(chunk, targets[0])
        for chunk in common[:-1]
    ]
    deferred.append(common[-1])
    return deferred


def _remove_redundant_interobject_waits(prefix: Sequence[str], common: Sequence[str]) -> List[str]:
    """Remove redundant thermal waits only from inter-object preludes."""
    requested: Dict[str, float] = {}
    confirmed: Dict[str, float] = {}
    for chunk in prefix:
        _process_thermal_commands(chunk, requested, confirmed, False)

    optimized: List[str] = []
    for index, chunk in enumerate(common):
        marker = LAYER_RE.search(chunk)
        if marker is None:
            raise ValidationError("common layer has no layer marker")
        prelude = chunk[:marker.start()]
        layer = chunk[marker.start():]
        # The first object has no inter-object prelude. For later objects, only
        # the section before LAYER:0 may lose redundant waits.
        prelude = _process_thermal_commands(prelude, requested, confirmed, index > 0)
        layer = _process_thermal_commands(layer, requested, confirmed, False)
        optimized.append(prelude + layer)
    return optimized


def transform(data: Sequence[str], clearance: float, machine_height: float,
              allow_unvalidated_chamber_commands: bool = False) -> List[str]:
    """Pure transformation: receive chunks and return a new list.

    It does not query Cura, display windows, or write files. This separation
    keeps the algorithm easy to test, like a static method in Java.
    """
    # 1) Validate first. No partial output is generated until every check passes
    #    (fail-closed strategy).
    if not math.isfinite(clearance) or clearance < 2.0:
        raise ValidationError("safe clearance must be a finite value of at least 2 mm")
    if not math.isfinite(machine_height) or machine_height <= 0.0:
        raise ValidationError("machine height must be a finite positive value")
    if ";HYBRID_SEQUENCE:APPLIED" in "\n".join(data):
        raise ValidationError("the script has already been applied")

    # 2) Reconstruct the logical object and layer structure.
    object_runs = _split_object_runs(data)
    prefix = object_runs.prefix
    runs = object_runs.runs
    suffix = object_runs.suffix
    layer_chunks = [chunk for run in runs for chunk in run]
    # Cura keeps End G-code in the final layer chunk.  Its final TIME_ELAPSED
    # marker provides the only validated boundary after which modal shutdown
    # commands remain at the end and are not affected by this reordering.
    final_time = layer_chunks[-1].rfind(";TIME_ELAPSED:")
    if final_time >= 0:
        layer_chunks[-1] = layer_chunks[-1][:final_time]
    header_region = "\n".join(prefix)
    layer_region = "\n".join(layer_chunks)
    _validate_arc_moves(layer_chunks)
    has_unvalidated_chamber_commands = _validate_chamber_commands(
        layer_chunks, allow_unvalidated_chamber_commands
    )
    # Modes are sequential: an M82 in Start G-code is valid only if a later M83
    # leaves E relative before LAYER:0 begins.
    header_e_modes = re.findall(r"(?im)^\s*(M82|M83)(?:\s|;|$)", header_region)
    if not header_e_modes or header_e_modes[-1].upper() != "M83":
        raise ValidationError("absolute extrusion (M82) is unsupported; enable Relative Extrusion")
    if re.search(r"(?im)^\s*M82(?:\s|;|$)", layer_region):
        raise ValidationError("absolute extrusion (M82) appeared inside a layer")
    header_xyz_modes = re.findall(r"(?im)^\s*(G90|G91)(?:\s|;|$)", header_region)
    if header_xyz_modes and header_xyz_modes[-1].upper() == "G91":
        raise ValidationError("relative XYZ positioning (G91) remains active at the first layer")
    if re.search(r"(?im)^\s*G91(?:\s|;|$)", layer_region):
        raise ValidationError("relative XYZ positioning (G91) is unsupported")
    if re.search(r"(?im)^\s*G92\s+[^;\r\n]*\b[XYZ]", header_region + "\n" + layer_region):
        raise ValidationError("XYZ coordinate resets (G92) are unsupported")
    # 3) Preserve layer-0 chunks in their original order and prepare the rest.
    heights = [_max_z(run) for run in runs]
    common = _defer_common_hotend_transition(prefix, [run[0] for run in runs])
    common = _remove_redundant_interobject_waits(prefix, common)
    remainder: List[str] = []
    previous_height = max(_max_z(common), 0.0)
    for index, run in enumerate(runs):
        # To resume an object: rise, travel above its last known layer-0
        # position, and return to that Z. The LAYER:1 chunk then continues.
        safe_z = max(previous_height, _max_z(common)) + clearance
        if safe_z > machine_height:
            raise ValidationError("required safe Z ({:.2f}) exceeds machine height ({:.2f})".format(safe_z, machine_height))
        edited_first_remainder = _insert_transition(run[1], safe_z, _end_point(run[0]))
        remainder.extend([edited_first_remainder] + run[2:])
        previous_height = heights[index]

    # 4) Mark and assemble the output: header + common layers + objects.
    markers = ";HYBRID_SEQUENCE:APPLIED\n"
    if has_unvalidated_chamber_commands:
        markers += ";HYBRID_SEQUENCE:UNVALIDATED_CHAMBER_COMMANDS\n"
    if prefix:
        prefix[0] += markers
    else:
        common[0] = markers + common[0]
    return prefix + common + remainder + suffix


class HybridSequentialPrint(Script):
    """Adapter connecting the pure transformation to Cura's API."""

    def getSettingDataString(self) -> str:
        # Cura generates the script settings interface from this JSON.
        return json.dumps({
            "name": "Hybrid Sequential Print v{} (experimental)".format(SCRIPT_VERSION),
            "key": "HybridSequentialPrint",
            "metadata": {},
            "version": 2,
            "settings": {
                "common_layers": {
                    "label": "Common layers",
                    "description": "v{} supports exactly one common layer.".format(SCRIPT_VERSION),
                    "type": "int", "default_value": 1, "minimum_value": 1, "maximum_value": 1
                },
                "safe_clearance": {
                    "label": "Safe Z clearance",
                    "description": "Vertical clearance above the previously completed object.",
                    "unit": "mm", "type": "float", "default_value": 5.0,
                    "minimum_value": 2.0, "maximum_value_warning": 15.0
                },
                "allow_unvalidated_chamber_commands": {
                    "label": "Allow unvalidated heated-chamber commands",
                    "description": "Experimental: allow M141/M191 after G-code review and supervised testing.",
                    "type": "bool", "default_value": False
                }
            }
        })

    def execute(self, data: List[str]) -> List[str]:
        """Entry point called by Cura when G-code is saved."""
        stack = Application.getInstance().getGlobalContainerStack()
        try:
            # These properties come from the active profile, not G-code text.
            if stack is None:
                raise ValidationError("Cura's active printer profile is unavailable")
            machine_name = str(stack.getProperty("machine_name", "value") or "")
            machine_tier = _machine_tier(machine_name)
            if machine_tier is None:
                raise ValidationError("v{} requires an approved or test machine profile".format(SCRIPT_VERSION))
            if machine_tier == "test":
                Logger.log("w", "HybridSequentialPrint: using unvalidated test machine profile '%s'", machine_name)
            if stack.getProperty("print_sequence", "value") != "one_at_a_time":
                raise ValidationError("Special Modes > Print Sequence must be One at a Time")
            if not bool(stack.getProperty("relative_extrusion", "value")):
                raise ValidationError("Special Modes > Relative Extrusion must be enabled")
            if bool(stack.getProperty("support_enable", "value")):
                raise ValidationError("supports are unsupported in v{}".format(SCRIPT_VERSION))
            if str(stack.getProperty("adhesion_type", "value")) not in ("none", "skirt"):
                raise ValidationError("use Build Plate Adhesion = None or Skirt")
            machine_height = _setting_float(
                stack.getProperty("machine_height", "value"), "machine height"
            )
            safe_clearance = _setting_float(
                self.getSettingValueByKey("safe_clearance"), "safe clearance"
            )
            result = transform(
                data,
                safe_clearance,
                machine_height,
                bool(self.getSettingValueByKey("allow_unvalidated_chamber_commands")),
            )
            if ";HYBRID_SEQUENCE:UNVALIDATED_CHAMBER_COMMANDS" in "\n".join(result):
                Message(
                    title="Hybrid Sequential Print warning",
                    text="M141/M191 heated-chamber commands were reordered under an experimental override. Review the G-code and test only under supervision.",
                ).show()
            Logger.log("i", "HybridSequentialPrint: transformed %d G-code chunks", len(data))
            return result
        except ValidationError as error:
            # Fail closed: return the original content with a visible marker.
            # Never return a partially transformed file.
            message = "G-code was NOT changed: {}".format(error)
            Logger.log("e", "HybridSequentialPrint: %s", message)
            Message(title="Hybrid Sequential Print stopped", text=message).show()
            if data:
                data[0] += ";HYBRID_SEQUENCE:REJECTED {}\n".format(str(error).replace("\n", " "))
            return data
