// Business profile (v013): successful domain operations and reads only, against the
// single-event interface layer. No negative checks, no mutation identifiers, no directed
// fault-trigger sequences. Argument order follows interfaces.library.js: own id, userId, bookId.
const NUMBER_OF_USERS = 5;
const NUMBER_OF_BOOKS = 5;
const userSequence = new java.util.concurrent.atomic.AtomicInteger(1);
const bookSequence = new java.util.concurrent.atomic.AtomicInteger(1);
const loanSequence = new java.util.concurrent.atomic.AtomicInteger(1);
const holdSequence = new java.util.concurrent.atomic.AtomicInteger(1);

bthread("business.createUsers", function () {
  for (let i = 0; i < NUMBER_OF_USERS; i++) {
    let id = userSequence.getAndIncrement();
    createUser(id, "Reader " + id);
  }
});
bthread("business.createBooks", function () {
  for (let i = 0; i < NUMBER_OF_BOOKS; i++) {
    let id = bookSequence.getAndIncrement();
    createBook(id, "Book " + id);
  }
});
ctx.bthread("business.borrow", "UserBook.CanCreateLoan", function (pair) {
  createLoan(pair.userid, pair.bookid, loanSequence.getAndIncrement());
});
ctx.bthread("business.reserve", "UserBook.CanCreateHold", function (pair) {
  createHold(holdSequence.getAndIncrement(), pair.userid, pair.bookid);
});
ctx.bthread("business.return", "Loan.All", function (loan) {
  deleteLoan(loan.userid, loan.bookid, loan.loanid);
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
