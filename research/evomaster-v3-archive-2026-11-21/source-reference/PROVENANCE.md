# Recovered F/C source references

These files are provided to make the archived mutation definitions inspectable. They were recovered from public branch `codex/library-feature-mutants-v001` at commit `791816c91f39e26a10292f742269cd29ea87d9e7`.

They are not the byte-identical files used by the archived campaigns. The run inputs record different SHA-256 values:

| File | SHA-256 recorded by run | SHA-256 of included reference snapshot | Status |
| --- | --- | --- | --- |
| `library/sut/library_sut_netbox_gitea.py` | `faf5260a806009bbd11245418cc1cbaf5a83343597661953f83ea7b9393d875a` | `133ff2f4a4e836c3e76e79fec9eedb6b206edb946e3c3442df63c3ca54908847` | Reference only; mismatch |
| `library/feature-mutants-v001/server.py` | `c1fe3e6fe5d0583230dd66eb878d3f6a8af20f857ca6eae5a447e19423631bb1` | `26a6a5fd5e71db9a06a885fe2450b523ca5356d46e258ace80af6566e90e79cd` | Reference only; mismatch |

`library/sut/BUG_README.MD` documents B1-B6, F1-F6, and C1-C3. The C-set README explains its three directed witnesses. These documents describe the recovered reference implementation. Recover the exact run-hash files before claiming source-identical reproduction.
