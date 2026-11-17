// Labels drawn from a shared counter depend on thread scheduling, not on event selection.
//
// BPjs runs the b-threads' steps between two sync points concurrently. Three workers take a
// number from a shared counter before their first sync; which worker gets 1, 2 or 3 is decided
// by the thread scheduler, so the same event selection yields different traces from run to
// run. Any label a model needs should be derived from what the event is about (here: the
// worker's name), never from a counter shared by several b-threads.
//
// Run several times: provengo run --dry .   and compare which worker got which id.

const next = new java.util.concurrent.atomic.AtomicInteger(1);

["a", "b", "c"].forEach(function (name) {
  bthread("worker " + name, function () {
    let id = next.getAndIncrement();
    request(Event("work", { worker: name, id: id }));
  });
});
