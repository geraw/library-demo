import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('pilot', Path(__file__).with_name('pilot_library.py'))
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


class ReplayTests(unittest.TestCase):
    def test_generated_ids_and_json_encoded_bodies_compare_equal(self):
        def rows(user, book, loan):
            return [
                dict(method='POST', url='http://127.0.0.1:1/users', status=201,
                     input={'name':'A'}, response={'id':user,'name':'A'}),
                dict(method='POST', url='http://127.0.0.1:1/books', status=201,
                     input={'title':'X'}, response={'id':book,'title':'X'}),
                dict(method='POST', url='http://127.0.0.1:1/loans', status=201,
                     input=json.dumps({'userId':str(user),'bookId':str(book)}),
                     response={'id':loan,'userId':user,'bookId':book}),
                dict(method='DELETE', url=f'http://127.0.0.1:1/loans/{user}/{book}',
                     status=200,input=None,response={'message':'Loan deleted'}),
            ]
        self.assertEqual(pilot.canonical(rows(123456,456789,999999)),
                         pilot.canonical(rows(111111,222222,333333)))

    def test_different_outcome_is_not_normalized_away(self):
        row = dict(method='GET', url='http://127.0.0.1:1/books/123',
                   status=200, input=None,response={'id':123})
        other = dict(row, status=404, response={'error':'Book not found'})
        self.assertNotEqual(pilot.canonical([row]), pilot.canonical([other]))

    def test_transport_relocation_across_every_chunk_boundary(self):
        old = b'"url":"http://127.0.0.1:23443/'
        new = b'"url":"http://127.0.0.1:23501/'
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            for offset in range(-len(old),len(old)):
                content=b' '*(1024*1024+offset)+old+b'books", "callback":"base64-unchanged"'
                source=folder/'source.json'
                target=folder/'target.json'
                source.write_bytes(content)
                expected=content.replace(old,new)
                original, relocated, count=pilot.relocate_sample(source,target,23501)
                self.assertEqual(original,hashlib.sha256(content).hexdigest())
                self.assertEqual(relocated,hashlib.sha256(expected).hexdigest())
                self.assertEqual(target.read_bytes(),expected)
                self.assertEqual(count,1)
                target.unlink()


if __name__ == '__main__':
    unittest.main()
