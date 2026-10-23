# v003 changes and reasons

- Resolve a DIV-1 summary coverage gap only against its exact existing control-qualified raw pair. Require same journal, product/run, actual request field values, response statuses, and a unique source-linked create witness. This removes contradictory warnings without inventing additional findings. Same-class verified pairs are reported as verified comparisons, not differences.
- Compare explicit scalar REF-1 projections (strings/numeric IDs/null) as producer measurements. A missing key or `{ "missing": ... }` marker remains unknown. Boolean is not an integer ID. Array behavior remains unchanged. This fixes scalar values incorrectly labeled as missing evidence.
- Filter VIK-O09 coverage when Vikunja is absent. Preserve the exclusion under NOT_APPLICABLE in the audit, not as a missing-evidence warning. Mixed/Vikunja analyses retain the check.
- Deduplicate the two wrapper warnings for the same missing atomicity snapshots. Preserve the underlying limitation and its sources.
- Retain v001/v002, the original classifiers, catalogs and product gates. New composition uses preserved legacy workers, not new bug predicates. The historical-corpus and toolkit paths share the correction.

No full snapshot is reconstructed from applied/kept labels. No missing product semantics are generated from a product name. No original toolkit raw archive is included here. Recorded-result regression audits are labeled separately from original-archive reanalysis.
