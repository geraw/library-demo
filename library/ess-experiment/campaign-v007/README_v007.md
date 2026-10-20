# Neutral OpenAPI contract and unguided control-coverage pilot v007

The default contract and library_openapi_v007.json describe the same 13 API operations.
They contain no mutation-specific thresholds or scenario descriptions. The previous
contracts remain in Git history and in existing campaign directories; prior measurements
retain their original contract hashes and are not reclassified as v007 measurements.

Changes: flatten the User, Book and Hold response schemas; document positive integer
identifiers; specify JSON Error and Message responses; document existing 400 responses
for book detail and loan query validation; replace experimental prose with neutral API text.
No API path, request field, operation ID, SUT or generated scenario is changed.
No shared identifier types, OpenAPI links, RESTler annotations, seeded identities,
custom dependency map or prescribed tool sequences are supplied.

The v004 Provengo runner executes its prepared JavaScript model. It copies this JSON
for baseline tools and does not interpret the OpenAPI descriptions to generate that model.
This statement is specific to that runner, not a claim about other generators.

Run Invoke-ISSTA-Contract-Pilot-v007.ps1 with the original -CampaignPath and optional
-PreviousPilot. It creates a separate directory, copies the exact SUT and the new
contract, and runs RESTler then EvoMaster against the unmutated fixture for 60 seconds
each. Compilation, startup, finalization and optional installation are additional time.
Previous binary paths are reused when supplied. -Tools selects one tool; -Seconds
accepts 30..300. The v006 local installation options remain available.

Tool settings and the engine budget use the same numeric seconds. All mutations are
disabled. V007_REVIEW_ZIP contains provenance, the actual input contract, native outputs,
HTTP logs and coverage-summary.json. The native v006 runner may print PILOT_V006_COMPLETE;
that is process completion only. V007 prints a separate control-coverage status.

Coverage is ready only when the tool itself successfully creates a loan and a hold,
returns a loan and cancels a hold, has no observer errors or semantic control violations,
and exits without a timeout. Missing coverage is an experimental result, not permission
to supply an identifier map. V007 never automatically starts a mutant search.

Validation performed during development: 22 real unmutated Flask responses matched the
new schemas; structural checks preserved the 13-operation boundary and found no guidance
fields/trigger prose; mocked orchestration verified both tools receive 60 seconds and
mutations=none. This development validation is not a sequence supplied to either tool.
Actual Windows compilation and unguided tool coverage must be checked by the pilot.
