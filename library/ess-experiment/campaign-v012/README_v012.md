# v012: continue on the work machine using Git only

No downloaded study ZIP and no access to the home machine are required. The installed local Provengo JAR is used without replacement. This is a new work-machine configuration when its SHA256 differs from the home JAR; it is not labelled an identical reproduction.

From the repository root:

```powershell
git pull --ff-only origin master
if ($LASTEXITCODE -ne 0) { throw 'Git update failed.' }
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& .\library\ess-experiment\campaign-v012\Invoke-ISSTA-Work-v012.ps1
```

Requirements: repository `.venv` with Flask, a compatible Java JDK and local Provengo. Default JAR is `C:\Program Files\Provengo\Provengo Cli\Provengo.uber.jar`. Override with `-ProvengoJar`; `-Java` selects java.exe. No binaries are installed or upgraded. To only prepare inputs, add `-PrepareOnly`.

`frozen_inputs_v012.json` contains 18 small files: the exact model/SUT/OpenAPI/profile bytes from `java-fixed-split-v011-20261020-201115-48880-review.zip`, plus its original environment metadata. Base64 storage avoids Git newline conversion changing the frozen inputs. Every restored file is hash-checked. No samples, execution logs, credentials or JARs are bundled. The original environment has only study paths and configuration, retained as historical metadata; it is never used to locate the work JAR.

Each invocation restores a new `runs/work-reference-v012-*` directory, writes a new environment manifest for the selected local JAR and a `work-provenance.json` containing original/current JAR hashes and source-archive provenance. It does not rewrite previous runs or the installed JAR. v011 copies this provenance into its review ZIP.

The launcher then runs the unchanged v011 execution and scenario selection: mandatory positive loan/RTV and negative status self-checks, followed by 542 fixed scenarios on control, bugs 1/2/3/5 and bug 4. No sample is generated and no scenarios are extended. A JAR API incompatibility or failed self-check aborts before scoring. Existing strict-catalog coverage limitations remain; see README_v011.md.

The output still reports `V011_REVIEW_ZIP` because v011 performs the experiment. `WORK_RUN_V012_COMPLETE` means its invocation succeeded, not that all tests passed or all seeded bugs were found. Native failures and the independent observer remain separate evidence. In this commit v011 changes only to retain optional work-machine provenance; actuation and scoring are unchanged.
