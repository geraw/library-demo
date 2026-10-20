# Focused automatic-configuration audit v008

Decision: retain the tool builds and search configuration used in v007. Do not add
manual producer-consumer bindings, annotations, seed objects or supplied sequences.
Do not gate mutant testing on successful relational-resource coverage.

## Evidence inspected

- v007 native RESTler Compile/config.json: ResolveBodyDependencies=true and
  ResolveQueryDependencies=true. These are the documented automatic inference switches
  for body and query consumers. ResolveHeaderDependencies=false does not explain the
  missing user/book identifiers: this API has no identifier consumers in headers.
- v007 generated RESTler grammar: loan/hold userId and bookId remain fuzzable integers;
  the loan return user_id still consumes the loan's id. This is generated output, not
  an identifier substitution performed by the experiment proxy.
- EvoMaster 5.0.2 installed help: useResponseDataPool defaults true;
  bbProbabilityUseDataPool defaults 0.8; thresholdDistanceForDataPool defaults 2.
  The runner does not override these options. Automatic response-data reuse is thus
  not disabled by our invocation. This is a name-matching heuristic, not guaranteed
  semantic binding or proof that both resources are still alive when reused.
- EvoMaster 5.0.2 official EMConfig.kt confirms those defaults. Its advanced
  resource strategies have algorithm/mode eligibility conditions; enabling such flags
  blindly is not a demonstrated repair for the current black-box SMARTS run.

No clearly disabled central automatic inference mechanism was identified in this
focused check. This does not prove every alternative setting or later tool version
would behave identically. Optional strategies, cleanup changes, GET producers,
matching-distance retuning and version upgrades are not silently introduced after
observing the faults. They would constitute separately declared configurations.

## Frozen mutant pilot

Use the identical neutral v007 contract and SUT bytes, identical installed binary
hashes, seed and native settings. Change only the declared search duration (600s per
tool instead of the 60s control) and activate all five seeded mutations. Run RESTler
then EvoMaster, with a separate empty-state fixture for each. No additional control
run, sampling step, dependency injection or minimum business-coverage gate.

Record contract, SUT and binary hashes and the actual commands. Review native tool
findings separately from observer candidates. Previously observed very-long-integer
500s are outside the five seeded mutations; do not count them toward the five-bug score.
The RESTler results-analyzer failure must also be distinguished from search completion.

## Primary references

- https://github.com/microsoft/restler-fuzzer/blob/main/docs/user-guide/CompilerConfig.md
- https://github.com/WebFuzzing/EvoMaster/blob/v5.0.2/core/src/main/kotlin/org/evomaster/core/EMConfig.kt
- The archived v007 installed help and compiler output are the version-specific
  evidence. The RESTler main-branch documentation is explanatory, not a claim that
  the installed build equals the latest source revision.
