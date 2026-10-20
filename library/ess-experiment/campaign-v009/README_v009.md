# Fresh ten-sample generation and split replay timing v009

Copies and verifies the frozen business model and SUT from the original campaign;
uses the neutral v007 contract and the same Provengo JAR hash. No old samples are reused.
Generates ten new scenarios in two native batches of five, with the existing 500-event
length bound and existing model resource/history bounds. No ranking or fault-directed
selection is introduced. Native sampling may deduplicate identical serialized samples,
as in v004; all attempts and costs remain in sampling.json.

Runs the new ten against the unmutated fixture for validation, then replays exactly
those ten with bugs 1,2,3,5 together and bug 4 alone. Each case starts empty with a fresh
JVM. Existing native fail-fast behavior is retained; masking between bugs remains possible.
The improved v006 observer transport is used in every arm. Samples are hashed and
checked before every replay. Existing campaign directories and samples are untouched.

Reports preparation, native sampling, control validation and each mutant replay separately.
The combined research timing charges sampling ONCE plus the two mutant replays.
Standalone arm timings each include full sampling plus that arm's replay; do not sum
those two standalone totals because that would charge shared sampling twice.
Total elapsed time also includes validation and orchestration. Packaging is excluded.
Model-authoring time, Java compilation and Java guided tests are not charged here.

V009_REVIEW_ZIP contains the sample files, manifests, model, native logs, HTTP/oracle
logs, readable action tables, candidate diagnostics and timings.json. Candidate labels
are diagnostic, not a substitute for reviewing native outcomes and control evidence.
Only first clean discrepancies per scenario are classified; later effects remain separate.

Next phase: the repository's StrictGuidedRun.java runs pre-written scenarios through
the Provengo model without sample generation. It is a guided reachability runner,
not an independent JUnit suite or an unguided search baseline. Its results must be
classified from actual HTTP behavior, not just REACHED/STUCK or process exit code.
It hardcodes the old reset endpoint and catches actuator exceptions, so those details
need a versioned adapter before comparing it against the mutant fixture. V009 does
not alter or execute that Java source. Keep this next phase separate from sample timing.
