"""Deterministic fixture verification, not a discovery campaign. Run from any directory."""
import unittest
import sut_buggy_issta as sut

class Mutations(unittest.TestCase):
    def setUp(self):
        self.client = sut.app.test_client()
    def setup_case(self, bugs):
        sut.BUGS = set(bugs)
        self.client.post("/reset", json={})
        user = self.client.post("/users", json={"name": "Reader"}).get_json()["id"]
        books = [self.client.post("/books", json={"title": "Book " + str(i)}).get_json()["id"] for i in range(4)]
        return user, books
    def loan(self, user, book):
        return self.client.post("/loans", json={"userId": user, "bookId": book})
    def test_all_five_controls_and_mutations(self):
        # Every case is checked with no bugs, its single bug, and all five bugs.
        for bug in range(1, 6):
            for enabled in (set(), {bug}, {1, 2, 3, 4, 5}):
                with self.subTest(bug=bug, enabled=enabled):
                    user, books = self.setup_case(enabled)
                    faulty = bug in enabled
                    if bug == 1:
                        for book in books[:3]:
                            self.assertEqual(self.loan(user, book).status_code, 201)
                        self.assertEqual(self.loan(user, books[3]).status_code, 409 if faulty else 201)
                        self.assertEqual(len(self.client.get("/loans").get_json()), 3 if faulty else 4)
                    elif bug == 2:
                        for _ in range(2):
                            self.assertEqual(self.loan(user, books[0]).status_code, 201)
                            self.assertEqual(self.client.delete(f"/loans/{user}/{books[0]}").status_code, 200)
                        self.assertEqual(self.client.get("/loans").get_json(), [])
                        self.assertEqual(self.loan(user, books[0]).status_code, 409 if faulty else 201)
                    elif bug == 3:
                        for book in books[:2]:
                            self.assertEqual(self.loan(user, book).status_code, 201)
                        self.assertEqual(self.client.delete(f"/loans/{user}/{books[0]}").status_code, 200)
                        remaining = self.client.get("/loans").get_json()
                        self.assertEqual([x["bookId"] for x in remaining], [] if faulty else [books[1]])
                    elif bug == 4:
                        response = self.client.get(f"/books/{books[0]}")
                        self.assertEqual(response.status_code, 404 if faulty else 200)
                        self.assertIn(books[0], [x["id"] for x in self.client.get("/books").get_json()])
                        if not faulty:
                            self.assertEqual(response.get_json()["id"], books[0])
                    else:
                        holds = []
                        for book in books[:2]:
                            response = self.client.post("/holds", json={"userId": user, "bookId": book})
                            self.assertEqual(response.status_code, 201)
                            holds.append(response.get_json()["id"])
                        self.assertEqual(self.client.delete(f"/holds/{holds[0]}").status_code, 200)
                        self.assertEqual([x["id"] for x in self.client.get("/holds").get_json()], [] if faulty else [holds[1]])
    def test_reset_clears_history(self):
        user, books = self.setup_case({2})
        self.loan(user, books[0])
        self.assertTrue(sut.loan_history)
        self.client.post("/reset", json={})
        self.assertEqual(sut.loan_history, {})

if __name__ == "__main__":
    unittest.main()
