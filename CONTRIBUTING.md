# Contributing

Open an issue before expanding the compatibility envelope. Include the Cura version, printer profile, complete project settings, unmodified G-code, transformed G-code, and a minimal model. Never upload proprietary models or credentials.

Changes to parsing or motion generation require tests for acceptance and rejection paths. Safety checks should fail closed: uncertain input remains unchanged.

## Documentation languages

The root `README.md` and general project documents are maintained in English.
The code guide and roadmap are maintained as synchronized bilingual pairs:

- `docs/guia-del-codigo.md` (Spanish) and `docs/code-guide.md` (English);
- `docs/roadmap.md` (Spanish) and `docs/roadmap.en.md` (English).

Changes to either member of a bilingual pair must update its counterpart in the
same change. Decide whether any new document will be English-only or bilingual
before creating it.
