# Native Gitea baseline artifacts (g015)

The g015 gateway extends the common classifier to EvoMaster report JSON,
Schemathesis 4 ScenarioFinished NDJSON and Gitea access logs. It does not use
the historical Vikunja-only native adapter. No saved Python test is imported
or executed and no requests are sent.

Extract the original ZIP into a directory containing `evomaster_rep1`, etc.
Normalize Windows ZIP member backslashes into directory separators when
extracting on Linux. Then, from the repository root:

```powershell
python .\tools\natchan-v014\g015_gateway.py --input C:\path\to\extracted-g015 --output C:\path\to\new-natchan-g015
python -m unittest discover -s .\tools\natchan-v014\tests -p test_g015_gateway.py -v
```

The output directory must not already exist. Standard-library Python is enough.
Outputs: `analysis.json`, `summary.json`, `report.md`.

Every classified observation identifies original file bytes and record. The
gateway decodes base64 request/response bodies without executing them, counts
all retained exchanges, preserves native check details and classifies anomalous
exchanges with the existing catalog. Duplicate recorder snapshots are removed;
physical retries remain separate. Every EvoMaster fault entry is retained,
including inconsistent `totalNumber` counters.

The common classifier handles HTTP server errors. Other native assertions are
reported as native claims, not independently established semantic defects.
In particular, native `ignored_auth` severity is not an analyzer security verdict.
No exact contract was bundled in this g015 archive for independent conformance
checking. No unknown observation is force-matched to a known business bug.

For EvoMaster, retained access logs supply actual response status evidence;
native code 100 entries remain separate claims. Test-source status assertions
are not treated as replay results. Full execution request bodies and snapshots
are unavailable. Log-message families are descriptive, counted separately;
adjacent messages are not automatically assigned to a specific request.

Five tests cover decoding, log/response separation, native counter mismatch,
duplicate snapshots versus physical retries, and unknown error signatures.
The six-run integration checked every metadata request/500 count against logs.
