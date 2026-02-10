# Diagram Rendering (PlantUML -> SVG)

Source of truth:
- `docs/diagrams/conciliador_architecture.puml`

Generated artifact (commit this file too):
- `docs/diagrams/conciliador_architecture.svg`

Notes:
- The diagram uses **C4-PlantUML** vendored under `docs/diagrams/c4-plantuml/` to avoid remote includes.
- It uses `!pragma layout smetana` to avoid a Graphviz dependency.

## Command (example)

Prereq: Java 17+ installed and on PATH.

```powershell
java -jar plantuml.jar -tsvg docs/diagrams/conciliador_architecture.puml
```

This writes `docs/diagrams/conciliador_architecture.svg` next to the source file.

## Tool versions (last render)

- PlantUML: `1.2026.1`
- Java: `Temurin-17.0.18+8` (JRE)
