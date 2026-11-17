// Independent checks chained in one b-thread are reachable only in that order.
//
// "check list" and "check detail" are independent, but one b-thread issues them in sequence,
// so "check detail" is offered only after "check list" was selected. A scenario (or a guided
// test) that needs the detail check first can never get it: the third b-thread, which blocks
// "check list" until the detail check happened, makes the run end with no check at all.
//
//   with CHAINED = true:  (no events at all - the program is stuck)
//   with CHAINED = false: check detail, detail seen first, check list
//
// Run: provengo run --dry .

const CHAINED = true;

if (CHAINED) {
  bthread("checks", function () {
    request(Event("check list"));
    request(Event("check detail"));
  });
} else {
  bthread("list check", function () { request(Event("check list")); });
  bthread("detail check", function () { request(Event("check detail")); });
}

bthread("wants the detail check first", function () {
  block(Event("check list"), function () { waitFor(Event("check detail")); });
  request(Event("detail seen first"));
});
