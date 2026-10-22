# Proposed Gitea identity, shared-resource and permission-transition study

Status: design only, 22 October 2026. No multi-identity live run has been
performed by this update. Start with the study's pinned Gitea 28.1.0 image;
record database and image digest for every run. Confirm each expected permission
against that version's actual role configuration before scoring it.

## 1. Identity is several dimensions

The API observes accounts, credentials, permissions and resource history, not
whether one human or two humans operate them. Keep human operator identity out
of the oracle. Distinguish these experimental cases explicitly:

| Case | Accounts / credentials | Primary question |
|---|---|---|
| Same account, two connections | A with two independent clients | Do clients observe the same authorized state? |
| Same account, two credentials | A with tokens A1 and A2; separately, optional browser sessions | Are credential scope/revocation and session state independent as documented? |
| One person, two accounts | A and B with separate credentials | Are account boundaries preserved when switching actors? |
| Two accounts, shared resource | A owner; B a declared read or write collaborator | Does each allowed operation work, with shared state visible consistently? |
| Two accounts, isolated resources | Private repos RA and RB | Are direct reads, writes and references confined to the declared policy? |
| Changing relationship | B invited, admitted, downgraded, removed or reassigned | Does the declared access policy follow the transition? |

The same scenario can be driven by one operator. Separate physical people are
unnecessary for testing two server-side account identities.

## 2. Minimal fixtures and controlled growth

Use two ordinary non-admin accounts A/B, a private repository RA, a private RB,
and one organization with explicit team membership. Bootstrap admin, if needed,
must be a separate fixture actor and never silently substitute for A/B.
Create a small issue/label/milestone/comment/release set through the public API.
Add C only later to distinguish another organization member from an outsider.
Record `/user` identity checks using each credential before the test sequence.

First prove a normal issue create/edit/read cycle with allowed actors. g018 had
no successful issue PATCH, so this is a prerequisite for interpreting failed
updates, not a reason to abandon other covered resources. Test controls and
anomalies separately. Avoid a large cross product until the controls work.

## 3. Ranked experiment bundles

### Bundle A: same account, independent clients

1. A1 creates an issue; A2 reads it.
2. A2 edits; A1 reads the changed fields.
3. Repeat with comments, labels and milestones using stable resource IDs.
4. Revoke A1 while retaining A2; check the version's documented behavior using
   fresh requests. Treat token scopes and browser sessions as distinct mechanisms.

This provides a consistency/session control, not cross-account authorization.

### Bundle B: shared private repository, two accounts

Establish the policy table before execution for each operation and account.
Use A as owner and B first as reader, then writer, then removed collaborator.
For each state: direct GET, list visibility, permitted create/edit/delete, and
representative denied mutations. Re-read by an independent allowed actor after
every denied mutation. A 403/404 response alone cannot establish no state change.

Candidate scenario: A creates issue -> grants B write -> B edits title -> A
verifies -> removes B -> B attempts another edit -> A verifies unchanged title.
Record successful removal completion before the negative probe. Preserve any
documented propagation allowance and distinguish pending from stable state.

### Bundle C: accounts with isolated resources and cross-references

Maintain RA/RB and references created by different actors. Probe read and write
paths separately, including arrays and scalar reference fields supported by the
contract and scope configuration. Distinguish absent, deleted, inaccessible,
wrong-repository and valid same-scope references; they are not interchangeable.
Check both create and edit and the resulting persisted reference set.

Do not assume every cross-repository reference is illegal: encode the actual
field semantics first. A request rejected with no mutation is a negative control.
Unexpected successful access, silent omission, 500 and partial persistence are
different findings, not a single generic access bug.

### Bundle D: permissions after rename, transfer and visibility changes

Combine the prior rename/transfer research direction with identity history:

- Rename RA; verify children and references through its current canonical path.
- Transfer RA to another permitted owner/organization; verify access for A and B
  against the declared post-transfer policy, including direct reads and lists.
- Remove B from a team; repeat accesses via direct repository, issue and comment
  routes, separating direct collaborator grants from team-derived grants.
- Private/public changes: define what intentionally becomes public before testing
  leakage. Account for redirects/aliases only when the version promises them.
- Team changes, including Owners: preserve administrative recoverability in an
  independent resettable fixture. Owner-team diagnostics alone are not a verdict.

This bundle targets long causal prefixes: valid access -> relationship change ->
resource transition -> later operation. It is more informative than independent
random requests because the expected access changes during the same scenario.

### Bundle E: interleaving and update consistency

Begin with **logical interleaving**, not simultaneous backend execution:
A reads -> B changes -> A updates from its prior view -> B reads. Compare same-field
and disjoint-field changes, and evaluate declared version/conflict behavior.
Then interleave permission removal or transfer before a pending actor's next
request. Do not call a stale write a lost-update defect unless the product
contract promises the relevant protection.

True overlap is a separate later experiment requiring barriers, independent
connections, timestamps, quiescence and a concurrency-specific oracle. It must
not be inferred from logical interleaving.

## 4. Analyzer inputs required before live experimentation

Keep the tool gateway and product policy gateway separate:

- Tool gateway: tool/run/seed, request ID, method/path/body, response, native claim.
- Product gateway: account ID, credential alias (never raw token), configured role,
  resource stable ID and canonical path, membership/permission transitions,
  independent before/after snapshots and policy version.
- Credential alias and connection/session alias are distinct. Actor labels alone
  do not prove who authenticated; retain a verified identity mapping.
- Log correlation needs request IDs where available. Do not join by proximity
  when multiple actors or requests could match.
- Keep fixture and observer requests distinct from tool-generated requests.
  An oracle probe is not additional tool coverage or native detection.

Proposed observation metadata (a design, not an implemented v015 input adapter):

```json
{
  "actor_id": "account-B",
  "credential_alias": "B-token-1",
  "connection_alias": "client-B-2",
  "resource_key": "repository-id-2",
  "policy_revision": "after-remove-B",
  "transition_request_id": "req-17",
  "request_id": "req-18",
  "expected_capability": "deny_write",
  "expectation_basis": "versioned-role-policy",
  "before_snapshot_ref": "snapshot-17",
  "after_snapshot_ref": "snapshot-18"
}
```

## 5. Proposed evaluation families

| Family | Minimum evidence | Verdict boundary |
|---|---|---|
| Authorized consistency | Verified identity, allowed write, independent read | Compare declared persisted fields; respect permitted server normalization |
| Denied-write integrity | Declared deny, response, before/after independent read | Denial with mutation is separate from unexpected success |
| Access revocation | Successful transition, policy, later authenticated probe | Check after documented stable boundary; missing timing is unevaluable |
| Isolation | Two verified actors and scoped resources, explicit policy | Distinguish valid sharing from unauthorized access |
| Reference scope | Field relationship policy and persisted IDs | Wrong-scope, missing and inaccessible are separate cases |
| List/direct agreement | Same actor, stable resource, direct and list results | Honor pagination, filters and intentionally hidden resources |
| Failed-write atomicity | Full preimage, attempted changes, independent readback | Do not infer partial persistence from 500 alone |
| Stale-view handling | Read revisions, ordered writes and declared conflict semantics | A 409 may be correct behavior; lack of 409 is not automatically a bug |

These future rules are not claimed to be implemented in v015. Add them through
the existing generic observation/policy architecture with synthetic positive,
negative and missing-evidence cases, then validate on retained raw live traces.

## 6. Fairness and reporting

All tools should receive the same fixture data, contract scope, actors and reset
policy. Record how each tool can actually use multiple credentials. A tool that
cannot express an actor transition in the tested configuration is not silently
given an analyst-written equivalent and credited with finding it.

Report separately: permitted-state coverage, trigger reached, generic anomaly,
semantic oracle detection, known-bug association, native report and replay result.
Measure preparation and per-run time independently. Preserve the original g015
unseeded baseline and g018 seeded baseline as different configurations.

Recommended next live pilot: A + B above, with two accounts and independent
credentials, fixed short scenarios and complete trace capture. Expand to C/D
only after allowed and denied controls succeed. No new campaign runner is part
of this analyzer update.
