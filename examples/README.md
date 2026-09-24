# Examples

`two_cubes_synthetic.gcode` is a parser fixture, not printer-ready G-code. Real examples must be generated and reviewed from the documented Cura profile.

`BodyBox x4.gcode` is the original Cura 5.12.0 export for four small test
objects. `BodyBox x4 hybrid.gcode` is its transformed counterpart and completed
a supervised physical print successfully. These files demonstrate one tested
configuration; they are not universal printer-ready examples.

Cura `.3mf` project files are intentionally excluded because they can embed
local paths, personal profile names, preferences, and installed-plugin metadata.
