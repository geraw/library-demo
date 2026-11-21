# Library feature mutants v001

This third set adapts the semantic composition idea from [FeatureFuzz](https://doi.org/10.1145/3830454.3832578) into three opt-in Library defects. These are synthetic mutants. Each is a separate server configuration using the frozen v003 original API implementation.

| Fault | Trigger | Public evidence |
|---|---|---|
| C1 | Create loans for distinct borrowers and books, then read only one borrower's loans. | The filtered GET is correct. An unfiltered GET loses the other active loan. |
| C2 | Create two distinct holds for the same user and book, then cancel one hold by ID. | The hold list loses both. Holds for other pairs remain. |
| C3 | Create books A and B, delete A, then create C. | The allocator mistakes the current row count for the next allocation slot and reissues B's ID. The book list contains both rows under that ID. Reading C by the returned ID produces B. |

C3 uses the existing random six-digit IDs. The fault uses the active row count to index a retained list of issued IDs. The witness needs no specially seeded numeric IDs.

From the repository root, use a Python environment with the pinned v003 requirements.

```powershell
python -m pip install -r .\library\mutants-v003\requirements.txt
python .\library\feature-mutants-v001\verify.py
python .\library\feature-mutants-v001\server.py --faults C1 --port 23242
```

Use `C2` or `C3` in place of `C1`. Omit `--faults` for the baseline. The verifier runs public HTTP witnesses through Flask's test client against a separately loaded original, the baseline, and all three isolated faults. It checks exact 2xx statuses, correct setup and control behavior, and divergence in the matching fault only. It does not estimate random detection rates.

