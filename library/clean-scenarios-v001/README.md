# Clean recorded scenarios, v001

84 cases, 11,154 requests, 2,634,027 bytes of JSONL (~2.51 MiB).
These are the compact HTTP scenarios used by the fast replay, NOT Provengo sample
JSON, NOT serialized Java callbacks, and NOT a new BP sampling distribution.

Each case contains successful original operations plus GET 404 absence checks.
Selection uses ORIGINAL responses, never mutant responses. Unexpected mutant 4xx
remain observable failures. Original order is preserved; order records the position
in the full source trace. Descriptions and recorded random IDs are source data.
The fast replay strips description annotations and rebinds generated IDs.
Rows contain method, URL, body, expected status and expected JSON response.
The recorded localhost URL is not an instruction to contact any running service.

The projected original and indexed baseline both passed all 84 cases in the local
v002 pilot. This does not qualify any mutant for rarity. Reusing these cases for
calibration cannot establish independent holdout performance.

manifest.json records source archive SHA256, per-case sizes, request counts, and
checksums over LF-normalized bytes, so CRLF Git checkouts can be verified as well.
Original large samples and source evidence are not modified or included.

To build a small input ZIP compatible with the existing replay engine, from repo root:

```powershell
python .\library\clean-scenarios-v001\build_input.py --output 'D:\Yeshayahu\Temp\clean-library-input.zip'
```

The output path must not already exist. Building this ZIP runs no scenario or SUT.
It is optional: all 84 individual JSONL scenario files are directly readable in Git.
Existing mutants-v002 can use this ZIP with -EvidenceZip for diagnostic replay, but
those mutants have already failed the requested rarity qualification. No new campaign
is necessary merely to validate this upload.
