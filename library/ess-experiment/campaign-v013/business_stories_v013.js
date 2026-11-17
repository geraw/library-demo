// Business profile (v013): successful domain operations and reads only, against the
// single-event interface layer. No negative checks, no mutation identifiers, no directed
// fault-trigger sequences. Argument order follows interfaces.library.js: own id, userId, bookId.
const NUMBER_OF_USERS = 5;
const NUMBER_OF_BOOKS = 5;

// Ids are derived, never counted (see lib_stories.js): the trace is a function of the selected
// events alone. The hold id includes how many holds the pair created before (DAL hold records),
// so it never repeats when a pair holds again.
function holdIdFor(userId, bookId) {
  var pairIndex = (asInteger(userId) - 1) * NUMBER_OF_BOOKS + asInteger(bookId);
  return pairIndex + holdsCreatedFor(userId, bookId) * NUMBER_OF_USERS * NUMBER_OF_BOOKS;
}

bthread("business.createUsers", function () {
  for (let id = 1; id <= NUMBER_OF_USERS; id++) {
    createUser(id, "Reader " + id);
  }
});
bthread("business.createBooks", function () {
  for (let id = 1; id <= NUMBER_OF_BOOKS; id++) {
    createBook(id, "Book " + id);
  }
});
ctx.bthread("business.borrow", "UserBook.CanCreateLoan", function (pair) {
  createLoan(pair.userid, pair.bookid);
});
ctx.bthread("business.reserve", "UserBook.CanCreateHold", function (pair) {
  createHold(holdIdFor(pair.userid, pair.bookid), pair.userid, pair.bookid);
});
ctx.bthread("business.return", "Loan.All", function (loan) {
  deleteLoan(loan.userid, loan.bookid);
});
ctx.bthread("business.cancelReservation", "Hold.All", function (hold) {
  deleteHold(hold.holdid, hold.userid, hold.bookid);
});
ctx.bthread("business.deleteReader", "User.CanDelete", function (user) {
  deleteUser(user.userid);
});
ctx.bthread("business.deleteBook", "Book.CanDelete", function (book) {
  deleteBook(book.bookid);
});
ctx.bthread("business.readReader", "User.All", function (user) {
  verifyUserExists(user.userid);
});
ctx.bthread("business.readBook", "Book.All", function (book) {
  verifyBookExists(book.bookid);
  verifyBookDetailExists(book.bookid);
});
ctx.bthread("business.readLoan", "Loan.All", function (loan) {
  verifyLoanExists(loan.userid, loan.bookid);
});
ctx.bthread("business.readReservation", "Hold.All", function (hold) {
  verifyHoldExists(hold.holdid);
});
