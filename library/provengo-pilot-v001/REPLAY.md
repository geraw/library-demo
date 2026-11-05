# Frozen-sample replay after truncated controls

Invoke-Library-Replay.ps1 -ReuseRun <old-run> uses the existing 100 sample files
and frozen original/mutant SUTs. No sampling command is executed. All source
hashes and the Provengo JAR hash are verified. The old run remains available.
New run directories are created alongside it.

First, case 12 runs on original and all-bugs-off, on port 23500. Both must finish
and pass native checks and the normalized trace comparison. The default case
watchdog is 7,200 seconds. -PreflightOnly stops after this pair.

After preflight, two independent Python gateway processes use ports 23501 and
23502. Worker 1 runs odd cases and worker 2 runs even cases. Each worker has its
own frozen model, mutable Provengo database, SUT process and logs. Each worker
runs original, baseline and B1-B6 in order, resetting before every case. A
timeout stops that worker immediately; worker failure terminates the other
worker's process tree. There is no retry loop.

Sample events embed their original HTTP URL. Each non-default-port replay
therefore streams a temporary copy replacing the event URL prefix only.
Callback serialization remains unchanged. Source and temporary hashes and the
replacement count are retained. Only one temporary sample per worker exists
at a time. Trace comparison removes transport host/port differences and binds
generated IDs by entity type and creation order. JSON-encoded bodies are parsed
before ID binding. Changes in statuses and response payloads remain visible.

The output aggregate includes 800 replays plus the two preflight replays.
The older Library passive oracle is retained. B3 also gets aligned first
divergence witnesses. Natchan analysis is not invoked by this runner.
The hardened B3 proposal is not included: these are the exact frozen mutants
from the sampled run. B6 still needs overlapping HTTP handlers and is explicitly
marked BLOCKED_BY_SERIAL_GATEWAY. Parallel workers do not create overlap within
one SUT instance.

Tests exercised randomized-ID/body normalization, detection of response
differences and lossless URL relocation across chunk boundaries. Actual
Provengo/Windows execution must be checked by the preflight on the home machine.
The 2-3 second gap in the supplied execution log remains unexplained.
