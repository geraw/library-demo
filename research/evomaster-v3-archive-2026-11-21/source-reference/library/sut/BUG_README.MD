# Library SUT Bug Sets

All three server entry points are in this directory. Each process binds to
`127.0.0.1` and activates at most one fault. Run the examples from the repository
root with your Python environment activated.

```powershell
python -m pip install -r .\library\mutants-v003\requirements.txt
```

| Set | Entry point under `library/sut/` | Default port | Fault selector |
|---|---|---:|---|
| Literature-based v003 | `library_sut_literature_v003.py` | 23600 | `--mode B1` through `--mode B6` |
| NetBox/Gitea archive-inspired | `library_sut_netbox_gitea.py` | 23601 | `--faults F1` through `--faults F6` |
| FeatureFuzz-inspired | `library_sut_featurefuzz.py` | 23602 | `--faults C1` through `--faults C3` |

## Command-line arguments

| Applies to | Argument | Accepted values | Default and behavior |
|---|---|---|---|
| Literature-based v003 | `--mode MODE` | `original`, `baseline`, `B1`, `B2`, `B3`, `B4`, `B5`, `B6` | Defaults to `baseline`, which runs the v003 framework with its faults disabled. `original` runs the clean reference implementation. A fault ID enables only that fault. |
| NetBox/Gitea | `--faults FAULT` | `F1`, `F2`, `F3`, `F4`, `F5`, `F6` | Defaults to all faults off. Supply one ID to enable it. |
| FeatureFuzz | `--faults FAULT` | `C1`, `C2`, `C3` | Defaults to all faults off. Supply one ID to enable it. |
| All | `--port PORT` | An available TCP port, passed as a decimal integer | Defaults to the port in the entry-point table. Point the test client to `http://127.0.0.1:PORT`. Give each concurrent process a different port. |
| All | `-h`, `--help` | No value | Prints help and exits. |

Fault IDs are uppercase. Start each process in a separate PowerShell window and
stop it with `Ctrl+C`. These commands start three fault instances on the default
ports and four optional controls on separate ports.

```powershell
python .\library\sut\library_sut_literature_v003.py --mode B2
python .\library\sut\library_sut_netbox_gitea.py --faults F1
python .\library\sut\library_sut_featurefuzz.py --faults C1

python .\library\sut\library_sut_literature_v003.py --mode original --port 23610
python .\library\sut\library_sut_literature_v003.py --mode baseline --port 23611
python .\library\sut\library_sut_netbox_gitea.py --port 23612
python .\library\sut\library_sut_featurefuzz.py --port 23613
```

## Literature-based v003

This set exercises stale relationship state, indexes, and caches after changes
to loans, holds, and books. See the [v003 README](../mutants-v003/README.md).

| ID | Observable behavior |
|---|---|
| B1 | Stale reservation state causes a valid loan request to be rejected. |
| B2 | Deleting one book silently removes a live loan for another book. |
| B3 | Deferred hold maintenance causes a later operation to affect the wrong hold. |
| B4 | A filtered loan query returns an obsolete loan ID after the loan is recreated. |
| B5 | A return targets an obsolete loan record and leaves the current loan active. |
| B6 | A catalog read returns a book that has already been deleted. |

## NetBox/Gitea archive-inspired

These synthetic faults adapt REST failure patterns from the two application
archives to the existing Library API.

| ID | Trigger and observable behavior |
|---|---|
| F1 | A user with an existing hold requests a loan for a different, available book. The valid loan request returns 400. |
| F2 | A user with a hold on one borrowed book places a hold on another borrowed book. The new hold is stored against the first book. |
| F3 | After a loan is returned with multiple holds still present, cancelling one hold reports success but leaves the target intact. |
| F4 | After a different user borrows a previously returned book, a query for that book and its former borrower returns the current borrower's loan. |
| F5 | A second user places a hold on a book. The creation response reports the first user's ID, while a hold-list read shows the correct ID. |
| F6 | Returning a book with another user waiting removes the loan, but the response reports HTTP 500. |

## FeatureFuzz-inspired

These synthetic faults combine resource identity, operation order, and shared
state. All requests in their directed witnesses succeed at the HTTP level.
A public read reveals the incorrect data. See the
[FeatureFuzz set README](../feature-mutants-v001/README.md).

| ID | Trigger and observable behavior |
|---|---|
| C1 | With two active loans, a filtered read returns the correct subset but removes the other loan from the shared collection. |
| C2 | Cancelling a hold by ID also removes a second hold for the same user and book. |
| C3 | After creating two books and deleting the first, the next creation reuses the surviving book's ID. A read by that ID returns the older book. |

Run the directed FeatureFuzz checks with:

```powershell
python .\library\feature-mutants-v001\verify.py
```

Run the directed NetBox/Gitea checks with:

```powershell
python .\library\sut\verify_netbox_gitea.py
```

