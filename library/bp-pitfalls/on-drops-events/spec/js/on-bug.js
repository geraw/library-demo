// on() drops events that are selected while its handler is still running.
//
// Provengo's on(eventSet, handler) is one b-thread looping `e = waitFor(eventSet); handler(e)`.
// While the handler is in a sync of its own, that b-thread is not waiting for eventSet, so an
// event of the set selected in that window is never handled - silently.
//
// Two pings are requested one after the other; the handler of each ping performs one sync of
// its own. A third b-thread forces the bad interleaving so the demo is deterministic: the
// handler's event is blocked until ping 2 has been selected.
//
//   expected: "handled ping 1", "handled ping 2"
//   with on():         only "handled ping 1"  (ping 2 is selected while the handler syncs)
//   with forEachEvent: both
//
// Run:  provengo run --dry .          (set USE_FOREACH to true to see the fix)

const USE_FOREACH = false;

const ping = function (n) { return Event("ping", { n: n }); };
const anyPing = any("ping");
const anyHandled = any(/^handled/);

bthread("pings", function () {
  request(ping(1));
  request(ping(2));
});

bthread("force the bad interleaving", function () {
  waitFor(ping(1));
  block(anyHandled, function () { waitFor(ping(2)); });
});

// One b-thread per event: the watcher is back at waitFor() as soon as it spawned the handler.
function forEachEvent(name, eventSet, handler) {
  bthread(name, function () {
    while (true) {
      let e = waitFor(eventSet);
      bthread(name + " " + e.data.n, function () { handler(e); });
    }
  });
}

function handle(e) {
  request(Event("handled ping " + e.data.n));
}

if (USE_FOREACH) {
  forEachEvent("handler", anyPing, handle);
} else {
  on(anyPing, handle);
}
