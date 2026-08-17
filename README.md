# Library Demo

This repository is organized as a system-by-system benchmark. The first system is the Library case study.

## Structure

```text
.
+-- README.md
+-- Library/
�   +-- README.md
�   +-- provengo/
�   �   +-- ... Provengo model and specification files
�   +-- sut/
�   �   +-- ... SUT implementation and execution scripts
�   +-- reference/
�   �   +-- ... OpenAPI, ground-truth, and reference artifacts
�   +-- notes/
�   �   +-- ... working notes and analysis
�   +-- scripts/
�       +-- ... helper scripts
+-- ... future systems such as Banking/, Directus/, etc.
```

## Purpose

This repository is the first public demo for a two-phase methodology:

1. OpenAPI -> Provengo model
2. Coverage-driven test-suite construction

The Library example is intentionally small and inspectable so that the method can be explained clearly before scaling to additional systems.

## Running the demo

This project is meant to run as a live system test: the Flask SUT stays running, and Provengo sends real HTTP requests to it.

### 1) Start the SUT

Open a terminal in the repository root and start the API server:

```bash
cd Library\sut
python sut.py
```

The SUT listens on `http://localhost:23242`.

If you prefer the included Windows helper, you can also run:

```bat
cd Library\sut
run_sut.bat
```

### 2) Run Provengo against the live SUT

Open a second terminal and make sure the `provengo` CLI is available in your PATH. Then execute the model against the running service:

```bash
cd Library\provengo
provengo run .
```

This is the real interaction mode: Provengo will generate randomized HTTP requests and validate the responses from the live SUT.

For a generated sample suite:

```bash
cd Library\provengo
provengo sample --overwrite --size 10 .
```

For an optimized suite:

```bash
cd Library\provengo
provengo ensemble --size 5 .
```

> Keep the SUT running in one terminal while you execute Provengo in another terminal.

### Typical workflow

```bash
# Terminal 1
cd Library\sut
python sut.py

# Terminal 2
cd Library\provengo
provengo run .
```
