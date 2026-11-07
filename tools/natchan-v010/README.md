# g012 Gitea variant result analysis v010

Offline analysis of the user-supplied `g012-gitea-variants-20261021-203735.zip`, SHA256 `93bbd055a88a57b4bb0d612ab8c2c37b2e454c6e46a751c112eb940640dab1fa`.

```powershell
python .\tools\natchan-v010\analyze_g012.py `
  --input 'C:\evidence\g012-gitea-variants-20261021-203735.zip' `
  --output '.\g012-analysis-new.json'
```

Optional exact-request comparison to the retained 28.1.0 SQLite g003 review archives:

```powershell
python .\tools\natchan-v010\analyze_g012.py `
  --input 'C:\evidence\g012-gitea-variants-20261021-203735.zip' `
  --sqlite-baseline-root 'C:\evidence\gitea-g003-work-20261021' `
  --output '.\g012-analysis-with-baseline-new.json'
python -m pytest .\tools\natchan-v010\tests -q
```

Requires Python 3.10+; analysis uses standard library only. Pytest is needed for tests. Original private archives are not bundled. Tests skip when their original inputs are unavailable; skipped tests are not validation passes.

The pipeline reuses v004 gateway/semantic witnesses, v005 augmentations and the v009 catalogs without changing their historical sources. The outer/inner native summaries, raw request/error counts, exact observed versions and source hashes are checked. Direct UTC unique method/path/status/time joins correlate all 83 error responses; no complete-sequential assumption or clock-offset adjustment is needed here.

Nightly has an unsupported known-bug catalog version. Its semantic predicate matches are reported separately as `nightly_behavioral_analogs_outside_catalog_versions`, never silently promoted to version-qualified known-bug matches. Nightly models still use the frozen 28.1.0 contract. The drift check preserves operation presence, not full schema equivalence. The exact development build is `29.0.0+dev-175-g33610142c3`, not an unspecified latest version.

See `reviews/REVIEW_g012.md` and `reviews/SUMMARY_g012.json`. Full local output contains raw evidence and is not included in public Git. No SUT requests or new live test runs were made by this analysis.
