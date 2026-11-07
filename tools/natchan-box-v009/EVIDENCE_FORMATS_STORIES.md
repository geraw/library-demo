# Evidence produced by the story runs (toolkit v2.5 – v2.10) — what an analyzer has to read

Facts about the evidence only, no analysis rules. The examples come from the cycle-5 packages of 2 Nov 2026 (Homebox
v0.27.1, Paperless-ngx 3.4.1, Label Studio 1.23.0) and are shortened with `…`. Everything here is generic: the same
names and fields on every system. Only the SUT's own log (`sut.log`) is in the system's own format.

## 1. Where the packages are

| Package | Produced by | File | Where |
|---|---|---|---|
| Story run | `poc/Run-V2x-Stories.ps1` → `toolkit/v2.x/stories/Run-Stories.ps1` → `run_stories.py` | `<sut>-stories-<yyyyMMdd-HHmmss>.zip` | the machine's `<StoriesRoot>\upload\` (home `D:\…\stories_runs\upload`); copies of the summary files in the repository under `results/<sut>-…/` |
| Baselines run | `baselines/v2/Run-Baselines-v2.ps1` | `<sut>-baselines-v2-<stamp>.zip` | the same `upload\` folder; format in `baselines/v2/README.md` |

`<sut>` is the system's runner name: `wger`, `vikunja`, `gitea`, `gitea-pg`, `mealie`, `tandoor`, `tandoor-sqlite`,
`kimai`, `dtrack`, `paperless`, `homebox`, `inventree`, `labelstudio`. One ZIP holds one run of ALL stories of one
system. The run is R1 or R2 by its time stamp only (the protocol's `RUNS.md` of each cycle names which is which).

## 2. Files in a story-run ZIP

```
ENV_stories.txt              key=value: sut, sut_version, toolkit, runner
SUMMARY_stories.txt          human summary, one block per story (section 6)
result_stories.json          THE machine-readable result of every story (section 3)
gateway-journal.jsonl        every HTTP exchange the stories made, one JSON object per line (section 4)
sut.log                      the SUT container's log for the run window (docker logs --since), the system's own format
stories-<sut>.json           the stories derived from the contract (section 7)
manifest_stories.json        {file path in the ZIP: sha256}
compiled/<story>/            the first attempt of every story (section 5)
compiled-<repair><k>-<story>/  a later attempt of one story after a run-time repair (section 5)
```

## 3. `result_stories.json`

Top level:

| Key | Meaning |
|---|---|
| `toolkit` | `v2.9`, `v2.10`, … |
| `sut`, `contract_sha256` | system and the SHA-256 of the contract the stories were derived from |
| `families` | the families compiled (comma list) |
| `runner` | `provengo` |
| `requests` | number of research requests (journal records of category `research`) |
| `http_5xx` | list of research requests answered 5xx: `{index, action, method, path, logical_id, status}`; `index` is the journal line |
| `stories` | one object per story (below) |

Per story:

| Key | Meaning |
|---|---|
| `story` | story id `<FAMILY>_<entity>[_<field or target>]`, e.g. `DELREF_entity_tagIds`, `ATOMIC_entity`, `EDGE_mailaccount` |
| `status` | `COMPLETED` (ran to the end, its checks are valid), `SETUP_FAILED` (stopped before its question: a fixture or setup request got an unexpected status), `NOT_APPLICABLE` (a precondition the story needs did not hold, e.g. "the referrer does not name the target after the setup") |
| `checks` | number of checks evaluated |
| `failed_checks` | checks with `pass: false` (section 3.1) |
| `observations` | checks with `pass: null`: recorded behaviour, never a failure (policies, refusals, trimming) |
| `rejected_create` | for `SETUP_FAILED`: `{path, status, response}` of the refused request |
| `stop` | the line that ended a story that did not complete |
| `fix_rich`, `fix_exist`, `fix_distinct`, `fix_via`, `fix_value`, `fix_method`, `fix_init` | run-time repairs that were applied to this story (they explain why a later attempt exists) |

### 3.1 A check

```
{"story": "EDGE_entity", "check": "update modelNumber=max+1: never 5xx", "expected": "<500", "observed": 500, "pass": false}
{"story": "COPY_entity", "check": "source INTRA-REF $.children[].tags[].parentId in $.tags[]", "expected": [], "observed": [], "pass": false, "detail": {"A": [], "B": []}}
```

`pass`: `true` held, `false` failed, `null` observation. `detail` (optional) carries the evidence the check compared.

## 4. `gateway-journal.jsonl`

One JSON object per line, in order; `index` is the line number from 0. Every request the stories send goes through
the tool's gateway and is recorded BEFORE it reaches the analyzer's eyes in any other file.

| Field | Meaning |
|---|---|
| `category` | `research` (a request of a story to the SUT), `infrastructure-error` (the gateway failed, no SUT answer; in v2.9 every later request of the run is refused), `request-timeout` (v2.10: the SUT did not answer within the limit; the story got 408; not a SUT answer) |
| `action` | `authenticate` (session opening, answered by the gateway with the identity check), `story_create`, `story_read`, `story_update`, `story_delete`, `story_action` |
| `logical_id` | `<story>_<step> <text>`, e.g. `DELREF_entity_tagIds_2 read tag`, `EDGE_mailaccount_63 create mailaccount with imap_port=negative`, `RT_entity_6 update entity.assetId` |
| `story_id`, `step_id`, `attempt_id`, `exchange_id` | the story, its step number, `<story>#<attempt>` (attempt 1 = `compiled/`, later ones = the `compiled-…` folders in order), a running number over the run |
| `method`, `path` | the request as sent to the SUT (path relative to the run configuration's base URL) |
| `input` | the request body as JSON (null for none) |
| `status`, `response` | the SUT's answer (status code, body as text) |
| `session` | `A` or `B` (two sessions of the same research user where a story needs them) |
| `t_utc`, `t_rel_ms`, `latency_ms` | time of the record, time since the run started, request latency |

Secrets never appear: the authenticate record shows `[static token from run configuration]`, other secrets `[REDACTED]`.

## 5. The story folders

`compiled/<story>/` (attempt 1) and `compiled-<repair><k>-<story>/` (later attempts) each hold one Provengo project:

```
spec/js/stories.stories.js    the story: storyRequest(method, url, body, expected codes, meta, callback) calls in order
spec/js/interfaces.stories.js the shared prologue (v2.10: + one KEY-PK line on contracts keyed by `pk`)
config/provengo.yml
native.log                    the Provengo run log of this attempt
```

`<repair>`: `retry` (FIX-RICH / FIX-EXIST / DISTINCT after a refused create), `value` (FIX-VALUE), `via` (VIA-PARENT),
`learned` (later stories rerun with what earlier stories learned), `method` (METHOD-405), `init` (PARENT-INIT). The
story's line in `result_stories.json` is its LAST attempt.

Lines of `native.log` the stories write (one JSON object after the tag):

```
STORY_LOGIN A
STORY_STEP {"id":"EDGE_entity_1 create entity","status":201}
STORY_CHECK {"story":"EDGE_entity","check":"create name=empty: never 5xx","expected":"<500","observed":422,"pass":true}
STORY_DONE EDGE_entity
```

`STORY_DONE` present = the story ran to its end. A Provengo line `FAIL: A REST call returned the unexpected response
code.` followed by `### Switching to test fail mode. ###` = the run stopped at that request (the later lines are
skipped, not sent).

## 6. `SUMMARY_stories.txt`

```
sut=paperless runner=provengo requests=1626 5xx=2
DELREF_mailrule_account status=COMPLETED checks=8 failed=0
   OBSERVED DEL-REF observation: policy: {"delete": 204, "referrers": "removed"}
EDGE_mailaccount status=COMPLETED checks=145 failed=2
   FAILED create imap_port=negative: never 5xx: expected "<500" observed 500
DELREF_mailrule_action status=SETUP_FAILED checks=0 failed=0 fix_rich=mailrule:action stop=…
   ATTEMPT SETUP_FAILED: {"path": "/api/mail_rules/", "status": 400, "response": "…"}
```

## 7. `stories-<sut>.json` (derived from the contract, before the run)

`entities`: per entity its collection `path`, `detail` route, `id_field`, create / update methods and `refs`
(`{field, target, shape: scalar | array | object | array-object | path | nested-…, required}`): the references between
resources the tool found in the contract. `stories`: the derived stories with `family`, `entity` / `referrer` /
`target`, `field`, `key` and the `oracle` text. The compiled set is in `compiled/…`; a derived story that did not
compile is absent there (or listed in `stories-unbound.json` inside a compile folder).

## 8. The families and the relation each one checks

Check names as the compiler writes them (`<f>` a field, `<v>` an edge value, `<t>` / `<r>` target / referrer); the
full set of a run is the `check` values of its `STORY_CHECK` lines.

| Family | Relation / behaviour under test | Typical checks |
|---|---|---|
| DELREF | delete a TARGET that referrers name; what happens to the referrers | `precondition: referrer k names the target`, `delete the referenced <t>: never 5xx`, `target after the delete`, `referrer k after the delete`, `both referrers treated the same`, observation `DEL-REF observation: policy` |
| STALE | write back a referrer's snapshot after its target was deleted | `write back the snapshot taken before the delete: never 5xx`, `stale write: no dangling reference`, observation `STALE observation: policy` |
| FANOUT | four referrers of one target; every view of the target lists all four; one deleted, exactly that one gone | named after the view and the referrer; observation `observation: no view of <t> lists its <r>` when no view exists |
| DUPBIND | the same referrer create sent twice | `second identical create: never 5xx`, `the first item is still readable`, `two items: the second is readable`, observation `DUP-BIND observation: policy` |
| PROJNEST / EMBED | a child read through its parent's view (nested place, embedded object) | named after the place (`$.a[].b[]`); EMBED `control: the target shows the new value`; observation `VARIANT observation: …` |
| MOVE | a child moved to another parent; it follows | `before the move: K listed in O1`, `move K to O2: never 5xx`, `K names its parent after the move`, observation `MOVE observation: move status` |
| ATOMIC | an update / create with a MISSING reference (id that does not exist) | `update <f> a missing reference: never 5xx`, `create <f> a missing reference: never 5xx`, `refused update: no partial commit of <f>`, `create and update agree on a missing reference`, observation `ATOMIC observation: policy` |
| COPY | a copy action; internal references of the copy point inside the copy | `source INTRA-REF …`, `copy response INTRA-REF …`, `copy readback by A INTRA-REF …`, `new identity`, `source arrays unchanged by the action` |
| RT | every writable field updated, read back | `update round trip: <f>`, `second update …`, never 5xx |
| EDGE | edge values on create and update | `create <f>=<v>: never 5xx`, `update <f>=<v>: never 5xx`, `create and update agree on <f>=<v>`, bound checks |
| AGG, SCALE, HELD, AUDIT, PREVIEW, OPENUM, CONTRIB | aggregates, scaled actions, held children, audit logs, delete previews, enumerated operations, contributions | named after the family |

## 9. Decision facts of the study (from the cycle protocols, not analysis rules)

- A candidate: a failed check (`pass: false`) in a `COMPLETED` story, or a research 5xx (also in a setup step).
- Not a finding: `SETUP_FAILED` without a 5xx, `NOT_APPLICABLE`, observations, `infrastructure-error` and
  `request-timeout` records.
- Known tool false positives of v2.9, fixed in v2.10: DELREF / STALE / FANOUT / DUPBIND on enumeration fields
  (Paperless-ngx `action`, `type`); COPY INTRA-REF with both sides empty (Homebox).
- The SUT log ties a 5xx to its cause by time (`t_utc` of the journal record) and, where the system logs one, a request
  id (Homebox: `rid=` / `req_id=` with `status=` on the `request finished` line).
