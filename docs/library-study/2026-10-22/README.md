# Library Study Reports

The 22 October 2026 study snapshot separates research interpretation from
engineering reproduction. Start with the research report for experimental
questions and results; use the engineering guide for installation, commands,
version identities, acceptance gates and archived-input requirements.

- [Research report](RESEARCH_REPORT.md)
- [Engineering guide](ENGINEERING_GUIDE.md)
- [Repository retention audit](REPOSITORY_RETENTION_AUDIT.md)
- [Evidence manifest](run-evidence-manifest.json)
- [Analyzer archive manifest](analysis-manifest.json)
- [Recomputed analyzer summary](analyzer-summary.json)

The Word exports are distributed in the accompanying report download; Git retains
the Markdown sources and export builder. To rebuild them beside
the Markdown sources:

```powershell
python -m pip install python-docx
python .\build_word_reports.py
```

Rendering and visual review must follow regeneration before distributing new
Word exports. Exact historical replay requires external archived samples and
native binaries; the repository does not contain them. The current Git-only
fixed-catalog entry point is campaign-v012, which delegates to v011.

No repository cleanup was performed. The retention audit is a proposal only.
