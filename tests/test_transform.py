import importlib.util
import pathlib
import sys
import types
import unittest

class DummyScript: pass

for name in ("cura", "cura.pp", "cura.pp.Script", "cura.pp.scripts", "UM", "UM.Application", "UM.Logger", "UM.Message"):
    sys.modules[name] = types.ModuleType(name)
sys.modules["cura.pp.Script"].Script = DummyScript
sys.modules["UM.Application"].Application = object
sys.modules["UM.Logger"].Logger = object
sys.modules["UM.Message"].Message = object

path = pathlib.Path(__file__).parents[1] / "HybridSequentialPrint.py"
spec = importlib.util.spec_from_file_location("cura.pp.scripts.HybridSequentialPrint", path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

class TransformTests(unittest.TestCase):
    def chunks(self):
        return [
            ";header\nM83\nG90\n",
            ";LAYER:0\nG0 X10 Y10 Z0.2\nG1 X20 Y10 E1\n",
            ";LAYER:1\nG0 X10 Y10 Z0.4\nG1 X20 Y10 E1\n",
            ";LAYER:2\nG0 X10 Y10 Z0.6\nG1 X20 Y10 E1\n",
            ";LAYER:0\nG0 Z5\nG0 X100 Y100 Z0.2\nG1 X110 Y100 E1\n",
            ";LAYER:1\nG0 X100 Y100 Z0.4\nG1 X110 Y100 E1\n",
            ";LAYER:2\nG0 X100 Y100 Z0.6\nG1 X110 Y100 E1\n",
            ";end\nM84\n",
        ]

    def test_cura_settings_expose_release_version(self):
        settings = module.HybridSequentialPrint().getSettingDataString()
        self.assertIn("v{}".format(module.SCRIPT_VERSION), settings)

    def many_objects(self, count):
        data = [";header\nM83\nG90\n"]
        for index in range(count):
            x = 10 + index
            data.extend([
                ";OBJECT:{}\n;LAYER:0\nG0 X{} Y10 Z0.2\nG1 X{} Y10 E1\n".format(index, x, x + 1),
                ";OBJECT:{}\n;LAYER:1\nG0 X{} Y10 Z0.4\nG1 X{} Y10 E1\n".format(index, x, x + 1),
            ])
        data.append(";end\nM84\n")
        return data

    def test_reorders(self):
        result = module.transform(self.chunks(), 5.0, 250.0)
        layers = [module._layer_number(c) for c in result if module._layer_number(c) is not None]
        self.assertEqual(layers, [0, 0, 1, 2, 1, 2])
        self.assertIn("APPLIED", result[0])
        self.assertEqual(sum("SAFE_TRANSITION" in c for c in result), 2)
        for chunk in (c for c in result if "SAFE_TRANSITION" in c):
            self.assertIn("G90 ; hybrid: absolute positioning\nM83 ; hybrid: restore relative extrusion", chunk)

    def test_rejects_absolute_extrusion(self):
        data = self.chunks(); data[0] = data[0].replace("M83", "M82")
        with self.assertRaises(module.ValidationError): module.transform(data, 5.0, 250.0)

    def test_allows_start_gcode_m82_overridden_by_m83(self):
        data = self.chunks(); data[0] = data[0].replace("M83", "M82\nM83")
        self.assertIn("APPLIED", "".join(module.transform(data, 5.0, 250.0)))

    def test_rejects_single_object(self):
        with self.assertRaises(module.ValidationError): module.transform(self.chunks()[:4] + [self.chunks()[-1]], 5.0, 250.0)

    def test_moves_cura_inter_object_prelude_with_next_common_layer(self):
        data = self.chunks(); data.insert(4, ";OBJECT_TRANSITION\nG0 Z10\n")
        result = module.transform(data, 5.0, 250.0)
        joined = "".join(result)
        self.assertLess(joined.index(";OBJECT_TRANSITION"), joined.index(";LAYER:1"))
        self.assertIn(";OBJECT_TRANSITION\nG0 Z10\n;LAYER:0", result[2])

    def test_skips_only_confirmed_redundant_interobject_temperature_waits(self):
        data = self.chunks()
        data[0] += "M140 S80\nM190 S80\nM104 S230\nM109 S230\n"
        data.insert(4, "M140 S80\nM190 S80\nM104 S230\nM109 S230\n")
        joined = "".join(module.transform(data, 5.0, 250.0))
        self.assertEqual(joined.count("SKIPPED_REDUNDANT_M190 S80"), 1)
        self.assertEqual(joined.count("SKIPPED_REDUNDANT_M109 S230"), 1)
        self.assertEqual(joined.splitlines().count("M190 S80"), 1)
        self.assertEqual(joined.splitlines().count("M109 S230"), 1)

    def test_keeps_interobject_wait_when_temperature_changes(self):
        data = self.chunks()
        data[0] += "M140 S80\nM190 S80\nM104 S230\nM109 S230\n"
        data.insert(4, "M140 S85\nM190 S85\nM104 S235\nM109 S235\n")
        joined = "".join(module.transform(data, 5.0, 250.0))
        self.assertIn("M190 S85", joined)
        self.assertIn("M109 S235", joined)
        self.assertNotIn("SKIPPED_REDUNDANT", joined)

    def test_keeps_wait_when_target_changes_away_then_returns(self):
        requested = {}; confirmed = {}
        module._process_thermal_commands("M104 S230\nM109 S230\n", requested, confirmed, False)
        module._process_thermal_commands("M104 S225\n", requested, confirmed, False)
        result = module._process_thermal_commands("M104 S230\nM109 S230\n", requested, confirmed, True)
        self.assertIn("M109 S230", result)
        self.assertNotIn("SKIPPED_REDUNDANT", result)

    def test_defers_hotend_transition_until_last_common_layer(self):
        data = self.chunks()
        data[0] += "M104 S230\nM109 S230\n"
        data[1] += "M104 S225\n"
        data[4] += "M104 S225\n"
        data.insert(4, "M104 S230\nM109 S230\n")
        joined = "".join(module.transform(data, 5.0, 250.0))
        self.assertEqual(joined.count("DEFERRED_COMMON_M104 S225"), 1)
        self.assertEqual(joined.splitlines().count("M104 S225"), 1)
        self.assertEqual(joined.count("SKIPPED_REDUNDANT_M109 S230"), 1)
        self.assertEqual(joined.splitlines().count("M109 S230"), 1)

    def test_accepts_repeated_unchanged_hotend_target_in_only_first_common_layer(self):
        data = self.chunks()
        data[0] += "M104 S220\nM109 S220\n"
        data[1] += "M104 S220\n"
        data.insert(4, "M104 S220\nM109 S220\n")
        joined = "".join(module.transform(data, 5.0, 250.0))
        self.assertIn("HYBRID_SEQUENCE:APPLIED", joined)
        self.assertNotIn("DEFERRED_COMMON_M104", joined)
        self.assertEqual(joined.count("SKIPPED_REDUNDANT_M109 S220"), 1)
        self.assertEqual(joined.splitlines().count("M104 S220"), 3)

    def test_accepts_12_object_equal_temperature_pattern_from_real_file(self):
        data = [";header\nM83\nG90\nM104 S220\nM109 S220\n"]
        for index in range(12):
            if index > 0:
                data.append("M140 S80\nM190 S80\nM104 S220\nM109 S220\n")
            repeated_target = "M104 S220\n" if index == 0 else ""
            data.extend([
                ";OBJECT:{}\n;LAYER:0\nG0 X{} Y10 Z0.2\nG1 X{} Y10 E1\n{}".format(
                    index, 10 + index, 11 + index, repeated_target
                ),
                ";OBJECT:{}\n;LAYER:1\nG0 X{} Y10 Z0.4\nG1 X{} Y10 E1\n".format(
                    index, 10 + index, 11 + index
                ),
            ])
        data.append(";end\nM84\n")

        joined = "".join(module.transform(data, 5.0, 250.0))
        self.assertIn("HYBRID_SEQUENCE:APPLIED", joined)
        self.assertNotIn("DEFERRED_COMMON_M104", joined)
        self.assertEqual(joined.count("SAFE_TRANSITION"), 12)
        self.assertEqual(joined.count("SKIPPED_REDUNDANT_M109 S220"), 11)

    def test_rejects_actual_transition_missing_from_one_common_layer(self):
        data = self.chunks()
        data[0] += "M104 S230\nM109 S230\n"
        data[1] += "M104 S225\n"
        data.insert(4, "M104 S230\nM109 S230\n")
        with self.assertRaisesRegex(module.ValidationError, "actual M104"):
            module.transform(data, 5.0, 250.0)

    def test_rejects_inconsistent_common_layer_temperature_targets(self):
        data = self.chunks()
        data[1] += "M104 S225\n"
        data[4] += "M104 S220\n"
        with self.assertRaisesRegex(module.ValidationError, "targets differ"):
            module.transform(data, 5.0, 250.0)

    def test_rejects_temperature_transition_missing_from_one_common_layer(self):
        data = self.chunks(); data[1] += "M104 S225\n"
        with self.assertRaisesRegex(module.ValidationError, "actual M104"):
            module.transform(data, 5.0, 250.0)

    def test_keeps_interobject_wait_without_prior_confirmation(self):
        data = self.chunks()
        data.insert(4, "M140 S80\nM190 S80\nM104 S230\nM109 S230\n")
        joined = "".join(module.transform(data, 5.0, 250.0))
        self.assertIn("M190 S80", joined)
        self.assertIn("M109 S230", joined)
        self.assertNotIn("SKIPPED_REDUNDANT", joined)

    def test_rejects_unnumbered_chunk_inside_numbered_layers(self):
        data = self.chunks(); data.insert(3, ";AMBIGUOUS\n")
        with self.assertRaisesRegex(module.ValidationError, "non-layer data"):
            module.transform(data, 5.0, 250.0)

    def test_rejects_non_monotonic_layers(self):
        data = self.chunks(); data[3] = data[3].replace(";LAYER:2", ";LAYER:3")
        with self.assertRaises(module.ValidationError): module.transform(data, 5.0, 250.0)

    def test_rejects_height_overflow(self):
        with self.assertRaises(module.ValidationError): module.transform(self.chunks(), 5.0, 4.0)

    def test_accepts_larger_object_counts(self):
        for count in (5, 10, 20, module.MAX_OBJECTS):
            with self.subTest(count=count):
                data = self.many_objects(count)
                result = module.transform(data, 5.0, 250.0)
                joined = "".join(result)
                layers = [module._layer_number(c) for c in result if module._layer_number(c) is not None]
                self.assertEqual(layers, [0] * count + [1] * count)
                self.assertEqual(sum("SAFE_TRANSITION" in chunk for chunk in result), count)
                for index in range(count):
                    self.assertEqual(joined.count(";OBJECT:{}\n".format(index)), 2)

    def test_rejects_more_than_preventive_object_limit(self):
        with self.assertRaisesRegex(module.ValidationError, "preventive safety limit"):
            module.transform(self.many_objects(module.MAX_OBJECTS + 1), 5.0, 250.0)

    def test_rejects_negative_layer_in_prefix(self):
        data = self.chunks(); data[0] += ";LAYER:-1\nG0 X0 Y0 Z0.1\n"
        with self.assertRaisesRegex(module.ValidationError, "negative layers"):
            module.transform(data, 5.0, 250.0)

    def test_allows_layer_one_to_resume_with_extrusion(self):
        data = self.chunks(); data[2] = data[2].replace(";LAYER:1\n", ";LAYER:1\nG1 E0.2\n")
        result = module.transform(data, 5.0, 250.0)
        transitioned = next(chunk for chunk in result if "SAFE_TRANSITION" in chunk)
        self.assertIn("G0 X20.000 Y10.000", transitioned)
        self.assertIn("G0 Z0.200 ; hybrid: descend", transitioned)

    def test_rejects_incomplete_common_layer_end_position(self):
        data = self.chunks(); data[1] = data[1].replace(" Z0.2", "")
        with self.assertRaisesRegex(module.ValidationError, "complete XYZ"):
            module.transform(data, 5.0, 250.0)

    def test_allows_feedrate_only_command_before_entry(self):
        data = self.chunks(); data[2] = data[2].replace(";LAYER:1\n", ";LAYER:1\nG0 F9000\n")
        self.assertIn("SAFE_TRANSITION", "".join(module.transform(data, 5.0, 250.0)))

    def test_ignores_layer_one_entry_shape_and_restores_common_endpoint(self):
        data = self.chunks(); data[2] = data[2].replace("G0 X10 Y10 Z0.4", "G1 F300 Z0.6\nG0 F6000 X10 Y10\nG1 F300 Z0.4")
        result = module.transform(data, 5.0, 250.0)
        transitioned = next(chunk for chunk in result if "SAFE_TRANSITION" in chunk)
        self.assertIn("G0 X20.000 Y10.000", transitioned)
        self.assertIn("G0 Z0.200 ; hybrid: descend", transitioned)

    def test_rejects_indented_absolute_extrusion(self):
        data = self.chunks(); data[0] = data[0].replace("M83", "  m82")
        with self.assertRaisesRegex(module.ValidationError, "absolute extrusion"):
            module.transform(data, 5.0, 250.0)

    def test_rejects_xyz_coordinate_reset(self):
        data = self.chunks(); data[0] += "G92 X0\n"
        with self.assertRaisesRegex(module.ValidationError, "coordinate resets"):
            module.transform(data, 5.0, 250.0)

    def test_allows_standard_relative_xyz_and_m82_in_ending(self):
        data = self.chunks(); data[-1] = "G91\nG1 Z10\nG90\nM82\nM84\n"
        result = module.transform(data, 5.0, 250.0)
        self.assertEqual(result[-1], data[-1])

    def test_allows_ending_embedded_in_final_cura_layer_chunk(self):
        data = self.chunks()
        data[-2] += ";TIME_ELAPSED:123.4\nG91\nG1 Z10\nG90\nM82\n"
        result = module.transform(data, 5.0, 250.0)
        self.assertIn(";TIME_ELAPSED:123.4\nG91", result[-2])

    def test_rejects_m82_before_final_time_elapsed_boundary(self):
        data = self.chunks(); data[-2] = data[-2].replace(";LAYER:2\n", ";LAYER:2\nM82\n") + ";TIME_ELAPSED:123.4\n"
        with self.assertRaisesRegex(module.ValidationError, "absolute extrusion"):
            module.transform(data, 5.0, 250.0)

    def test_rejects_non_finite_or_small_dimensions(self):
        for clearance, height in ((float("nan"), 250.0), (1.9, 250.0), (5.0, float("nan")), (5.0, 0.0)):
            with self.subTest(clearance=clearance, height=height):
                with self.assertRaises(module.ValidationError):
                    module.transform(self.chunks(), clearance, height)

if __name__ == "__main__": unittest.main()
