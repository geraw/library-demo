# Library Demo

This repository is organized as a system-by-system benchmark. The first system is the Library case study.

## Structure

```text
.
+-- README.md
+-- Library/
¦   +-- README.md
¦   +-- provengo/
¦   ¦   +-- ... Provengo model and specification files
¦   +-- sut/
¦   ¦   +-- ... SUT implementation and execution scripts
¦   +-- reference/
¦   ¦   +-- ... OpenAPI, ground-truth, and reference artifacts
¦   +-- notes/
¦   ¦   +-- ... working notes and analysis
¦   +-- scripts/
¦       +-- ... helper scripts
+-- ... future systems such as Banking/, Directus/, etc.
```

## Purpose

This repository is the first public demo for a two-phase methodology:

1. OpenAPI -> Provengo model
2. Coverage-driven test-suite construction

The Library example is intentionally small and inspectable so that the method can be explained clearly before scaling to additional systems.
