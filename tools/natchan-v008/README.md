# Family evidence audit v008

Correction to earlier coverage reports: `0 adapted measurements` does not mean no retained evidence. Several missing evaluations were adapter gaps. This supplemental, read-only audit opens nested ZIPs in memory and recomputes explicitly supported comparisons. It does not replace the v006 known-bug classifier or promote stored verdicts into independent proof.

## Actual inputs and results

Eighteen distinct journals were read: g005 home seeds 5–8, g007 work seeds 1–4, g009 work seeds 1–4, g009 cloud seeds 1–4, and two retained v164 nested journals. Exact duplicate journal bytes are counted once. See `reviews/summary.json` for every archive/member hash and scope.

| Family | Recovered evidence | Mechanical result / boundary |
|---|---|---|
| IDEM | 64 pairs of identical HTTP writes in g005; 32 writes in seed 6 | No 5xx in those pairs. Session identity equivalence and semantic idempotency are not assumed |
| CASCADE-1 | 171 successful same-target deletions followed by a same-session read, without an intervening same-path write | Zero still-readable same-target records; 171 other verification records need parent/child relationship resolution |
| ADJ | 518 probes paired with a same-case/path/logical-ID verification | Six probes returned 5xx; temporal trigger windows and confounders are not established here |
| EDGE-U | 126 unique pairs with the same field and actual input value | 28 response-class differences; compatible business preconditions remain separate. 531 update records lacked a unique matching create, 35 lacked a verified same value/field |
| KNOWN | 17 retry-attempt records from nested v164 journals | Recorded status, attempt, declared signature and elapsed-since-trigger retained; no independent lock cause or signature-definition validation |
| REF-1 | 72 readable ID projections | 48 differ from sent IDs; 19 other records lack readable projections. Difference is a symptom, not automatic policy violation |
| LINK-2 | 212 readable ID projections | 126 differ; 19 incomplete. Full readback bodies are unavailable |
| DIV-1 | 196 retained summary records | Indexed, not treated as independently recomputed findings; raw EDGE-U status comparisons are separate |
| ATOM-1-2 | 60 retained summaries | Still requires full state for independent proof; existing per-field producer measurements remain a separate evidence tier |

Counts are evidence occurrences and pairs, not unique bugs. Families overlap. Successful comparisons do not establish complete campaign coverage.

## Corrected interpretation

- REF-1, LINK-2 and DIV-1 are now explicit in the evidence-family interface. Their evidence strength is reported rather than inferred from the stored `verdict`.
- The g009 work study note explicitly documents Provengo confirmation of C2+ and C8, while C4–C7 were not reached. This corrects any implication that all extended reference findings lacked Provengo evidence. The note is a historical attribution; the audit does not infer a native tool finding merely from an external projection.
- The retained C8 atomicity record has `tag_name: kept`, readback 200 and `rolled_back`. That supports the producer's rollback measurement; it is not independent full-state reconstruction. C8 does not require partial commit to be a bug.
- Environment records pin g004 home to Gitea 28.2.0 and g005 home to 28.1.0. Versions must be read per cohort; no blanket version propagation or expansion of known-bug signatures was performed.
- Earlier v007's no-nested-archive limitation describes that inventory. v008 explicitly traverses nested ZIPs with five-level and 500 MB expansion limits, member hashes and independent journal scopes. Earlier v005 also had a specialized nested-archive adapter.

## Running

```powershell
python .\tools\natchan-v008\family_audit.py `
  --input 'C:\evidence\review_g005_s6.zip' `
  --input 'C:\evidence\v164-triggers-20261018-153232-redacted.zip' `
  --output '.\family-audit-new.json'
python -m pytest .\tools\natchan-v008\tests -q
```

Repeat `--input` for every original archive or gateway-journal JSONL. Existing output is rejected. No extraction, server calls, tool execution, hidden activation signals or stored verdict matching occurs. Journal hashes deduplicate inputs. A missing archive or malformed journal fails visibly. All IDs in full local output originate in supplied evidence; publish summaries rather than credential-bearing journals.

## Still incomplete

The supplied list is broader than this batch. g006, additional home cohorts, rtcascade-v173/v174, stage-v128/v129, amplification-v140/v141 and the remaining nested archives were not analyzed in this audit. The v144 IDEM ZIP could not be retrieved through the connector: fetch_file returned empty content and fetch_blob failed. That is an access/retrieval gap, not absent evidence or zero results. Its pinned Git blob is `25cdc158439b4f39cb6b910395cc2ca360716b02` at private-study commit `e8314ed30534b0e24581f8c84700eada02b51253`.

Next integration work is to bind cascade relationships from IR plus create/read evidence, validate ADJ triggers/windows and session identities, resolve EDGE-U preconditions, and normalize projected REF/LINK measurements into the shared classifier with their evidence tier preserved. Until then these results are supplemental evidence coverage, not full classifier coverage.
