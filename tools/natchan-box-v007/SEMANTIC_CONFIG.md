# Semantic metadata interface

`natchan-story-semantics/1` separates product data from generic rule code. It is analysis configuration, not observed server state or a list of expected bugs. Profiles do not contain expected response counts, seeds, bug IDs or prerecorded response values.

## Generate a profile

Use the original OpenAPI bytes and producer story IR containing `entities` and `stories`:

```powershell
python .\tools\natchan-box-v007\derive_story_semantics.py --contract C:\experiment\contract.json --derived-stories C:\experiment\stories-product.json --product product --output C:\experiment\story-semantics.json
```

No network, Java, Provengo or SUT is invoked. The profile records contract and IR SHA256 hashes. Relations/projections come from the contract-derived IR; operator meanings are parsed from descriptions such as `` `r` - Replace ``. Missing meanings are not guessed from enum order. Inspect the generated hypotheses before a frozen evaluation; deriving metadata is not a substitute for defining the intended oracle.

The bundled wger profile explicitly uses `--display-rounding-steps 0.5,1,1.25,2.5` to preserve the producer's existing display-quantization tolerance. Those steps are a recorded tolerance policy, **not a guarantee in OpenAPI**. A discrepancy compatible with those nearest-display steps remains an observation. Other discrepancies under unspecified rounding remain candidates with an uncertainty gap.

## Select the profile

An immutable package may contain `story-semantics.json`. To analyze existing packages without changing their bytes, add:

```json
"configuration": {"story_semantics": "story-semantics.json"}
```

Paths are relative to the request file. An external profile and an embedded one cannot both be selected. If neither is supplied, a bundled product profile may be used. Its `product` and `contract_sha256` must match the run. Profiles cannot supply an observed SUT version. A contract hash conflict is a coverage gap; a contradictory product is invalid input. The profile's original bytes/hash enter provenance.

## Fields

| Field | Purpose |
|---|---|
| `schema_version` | Exactly `natchan-story-semantics/1` |
| `product` | Canonical product identifier, matching evidence |
| `contract_sha256` | Binding to the exact OpenAPI bytes reported by the run |
| `entities` | Named entity data: create method/path, detail template, ID field and reference fields/targets/shapes |
| `projections` | Read route template, owner, root array flag and declared child places/parent places/reference fields |
| `arithmetic` | Config entity, parent reference, operator/iteration/value/mode fields and meanings, computed view path, item projection and output field |
| `rounding` | Explicit arithmetic policy: `unspecified`, `none`, `floor` or `half_up`; positive `quantum` when quantizing after every operation; optional tolerated nearest-display `display_steps` |
| `derivation_sources` | Hashes of the source contract and story IR |

Projection paths support only `$`, `$[]`, `.field` and `[]`, for example `$.groups[].items[]`; no executable expressions or arbitrary JSONPath filters. Entity and parent identities are scoped by declared routes/places, not by a globally matching integer. Grouped array roots and the producer's alternate first-level array shape are qualified by the actual positive preimage.

## Adding known bug names

Generic detection does not need a bug ID. `story_profiles.json` optionally links recomputed facts and paths to known behavior-signature candidates. This must remain separate from semantic metadata and version-qualified known-bug catalogs. Adding a new candidate after seeing a behavior is retrospective classification; it cannot be reported as prospective independent bug discovery.

## Unsupported or incomplete evidence

A new product with no profile still gets supported raw/generic analysis and an explicit semantic-profile gap. Unsupported profile schema/policy returns exit 3. Invalid supported metadata returns exit 2. Missing controls, ambiguous attempts, conflicting contract bindings and uncertain rounding remain gaps; no cached producer verdict supplies the missing proof. Full business semantics may require additional generic rules beyond those in this release.
