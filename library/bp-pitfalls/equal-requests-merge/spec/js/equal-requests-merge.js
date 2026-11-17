// Two b-threads request an EQUAL event (same name, same data). One selection satisfies both.
//
// A natural reading of "each checker requests its own check" is that two checks happen. In
// BPjs an event is identified by its name and data, so the two requests are one event, and the
// trace shows a single "check" followed by both "done" events.
//
//   expected by the author: check, check, A done, B done
//   actual:                 check, A done, B done        (one check for two requests)
//
// Run: provengo run --dry .

bthread("checker A", function () {
  request(Event("check", { id: 1 }));
  request(Event("A done"));
});

bthread("checker B", function () {
  request(Event("check", { id: 1 }));
  request(Event("B done"));
});
