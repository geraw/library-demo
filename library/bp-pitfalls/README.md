# BP modelling pitfalls, each as a minimal Provengo project

Every directory is a self-contained Provengo project (`provengo run --dry .`) that reproduces
one pitfall met while writing the library model. Each spec file states the expected and the
actual trace at its top.

| Project | Pitfall |
|---|---|
| `on-drops-events` | `on(eventSet, handler)` is one b-thread; events of the set selected while the handler syncs are never handled |
| `equal-requests-merge` | Two b-threads requesting an equal event (same name and data) are both advanced by one selection |
| `chained-checks` | Independent checks issued in sequence by one b-thread are reachable only in that order |
| `scheduling-dependent-labels` | A counter shared by several b-threads hands out numbers in scheduling order, so the same event selection yields different traces |
| `global-name-collision` | Spec files share one global scope; a same-named function in a later file silently replaces an earlier one |
