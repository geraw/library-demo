# All-five-mutant baseline pilot v006

Run RESTler first, then EvoMaster, with all five mutations enabled for each.
Each tool starts with a fresh managed localhost fixture and an empty-state check.
Each engine receives a 600-second search setting. Preparation and finalization are
extra wall time; a 690-second search-process watchdog preserves evidence and kills
only the launched process tree if the tool fails to exit.

The observer does not abort search on findings. Tools retain native sequence/pruning
behavior. State corruption and rejected producers may still block later operations.
This is a pilot, not the official 4+1 comparison. Do not merge its scores into that table.
Native bug reports and observer diagnostics must be assessed separately. Observer
ledger findings after the first discrepancy are tainted; campaign-global evidence
requires isolated replay before a sequence-local detection claim.

No custom bug-code overrides, analyst sequences or hand-written RESTler dependencies
are introduced. RESTler compiles the frozen campaign contract and runs fuzz with
bfs-cheap, seed 1, and the generated dictionary. EvoMaster uses black-box mode,
seed 1, and version-adaptive schema/target flags. The contract is unchanged.
Full HTTP/oracle logs, native reports, generated tests, compiler outputs, commands,
identity checks, timings and hashes are saved in a unique campaign subdirectory.
The REVIEW_ZIP includes all results, so its size depends on generated tool traffic.

```powershell
& .\library\ess-experiment\campaign-v006\Invoke-ISSTA-Baselines-v006.ps1 `
  -CampaignPath 'D:\Yeshayahu\Temp\library-demo\library\ess-experiment\runs\issta-business-v004-20261019-225558'
```

Binaries are discovered in the repository, its parent, Downloads, common tools
folders and C:\work\temp (bounded depth). If missing or ambiguous, specify
-EvoMasterJar and -RestlerPath (Restler.exe or Restler.dll). Environment overrides:
EVOMASTER_JAR, RESTLER_EXE, RESTLER_DLL. No binary is downloaded or installed.
Both binaries and EvoMaster flags are checked before the first search. Compilation
or search failure in RESTler is recorded and EvoMaster is still attempted.
Windows execution with the installed tool versions remains to be validated locally.
