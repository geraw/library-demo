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

Binaries are discovered in PATH, the managed cache, common folders and local fixed disks.
If a tool is missing, v006 installs it locally under `%LOCALAPPDATA%\ISSTA-tools-v006`.
No administrator rights or persistent PATH changes are used. Internet access is needed
for downloads, NuGet restore and Python packages. Installation time is outside search.

Use `-InstallLocalTools` to bypass old installations and prepare/reuse the pinned managed
tool distribution. Missing Java also triggers a portable JDK 21 installation.
EvoMaster is pinned to 6.2.0, with the release SHA256 verified. RESTler is built
from official commit 6d984deedbc54aad957fa3da0c7e9e5df23a2aee using the official
build-restler.py and a private .NET 8 SDK (Microsoft release SHA512 verified).
The engine gets its own Python venv based on the repository Python; dependencies
and resolved package versions are logged. RESTler upstream recommends Python 3.12.8;
compatibility with the machine's Python is checked by the build and pilot execution.
RESTler source ZIP is fetched by immutable commit over HTTPS; no independent signed
checksum is provided for that source archive. A manifest captures exact installed paths,
versions and binary hashes. The .NET SDK patch and portable JDK are resolved at first
installation and then cached. Installation failures retain logs and do not start search.

Explicit overrides: -EvoMasterJar and -RestlerPath (binary or installation folder).
Environment overrides: EVOMASTER_JAR, RESTLER_EXE, RESTLER_DLL.
`-InstallLocalTools` takes precedence over those existing-installation overrides.
Windows installation and execution with real binaries still require local validation.
