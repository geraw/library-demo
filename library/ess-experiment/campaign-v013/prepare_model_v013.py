"""Prepare a model snapshot of library/provengo (single-event interface layer) for a v013 run.

Profiles (business rules the DAL enforces):
  original  the repository model unchanged: one active loan per reader (matches library/sut/sut.py)
  contract  the experiment contract of sut_buggy_issta.py: no per-reader loan cap; one active loan
            per book; workload bounds on total loans/holds and on loans/holds per user-book pair
            (the same bounds the v004 campaign used - bounds, not server-side rules)

Stories:
  full      the repository's lib_stories.js (creates, deletes, reads and business-rule rejections)
  business  business_stories_v013.js: successful operations and reads only

The snapshot also points the interface layer at the given host/port (the observer on 23243 by
default), bounds scenario length, and copies the experiment fixture and contract next to it.
"""
import hashlib
import json
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Expected exactly one occurrence of: ' + old)
    return text.replace(old, new)


def set_counts(text, users, books):
    for name, value in (('USERS', users), ('BOOKS', books)):
        text, count = re.subn(r'const NUMBER_OF_' + name + r' = \d+;', 'const NUMBER_OF_' + name + ' = ' + str(value) + ';', text)
        if count != 1:
            raise RuntimeError('Missing entity count: ' + name)
    return text


def apply_contract(dal, loan_cap, hold_cap, pair_cap):
    dal = 'var v013PairLoans = {};\nvar v013PairHolds = {};\n' + dal
    dal = replace_once(dal, 'function createLoanEntity(data) {',
        'function createLoanEntity(data) {\n'
        '  var pairKey = data.userId + ":" + data.bookId;\n'
        '  v013PairLoans[pairKey] = (v013PairLoans[pairKey] || 0) + 1;')
    dal = replace_once(dal, 'function createHoldEntity(data) {',
        'function createHoldEntity(data) {\n'
        '  var pairKey = data.userId + ":" + data.bookId;\n'
        '  v013PairHolds[pairKey] = (v013PairHolds[pairKey] || 0) + 1;')
    dal = replace_once(dal,
        "return e.type === 'user-book' && !hasLoanForUser(e.userid) && !hasLoanForBook(e.bookid);",
        "return e.type === 'user-book' && !hasLoanForBook(e.bookid) && "
        "ctx.runQuery('Loan.All').length < " + str(loan_cap) + " && (v013PairLoans[e.userid + ':' + e.bookid] || 0) < " + str(pair_cap) + ";")
    dal = replace_once(dal,
        "return e.type === 'user-book' && (hasLoanForUser(e.userid) || hasLoanForBook(e.bookid));",
        "return e.type === 'user-book' && hasLoanForBook(e.bookid);")
    dal = replace_once(dal,
        "ctx.registerQuery('UserBook.CanCreateHold', function (e) {\n\treturn e.type === 'user-book';\n});",
        "ctx.registerQuery('UserBook.CanCreateHold', function (e) {\n\treturn e.type === 'user-book' && "
        "ctx.runQuery('Hold.All').length < " + str(hold_cap) + " && (v013PairHolds[e.userid + ':' + e.bookid] || 0) < " + str(pair_cap) + ";\n});")
    return dal


def prepare(repo, root, profile='contract', stories='full', users=5, books=5, host='127.0.0.1', port=23243,
            loan_cap=5, hold_cap=5, pair_cap=3, max_length=500):
    repo, root = Path(repo), Path(root)
    model = root / 'model'
    shutil.copytree(repo / 'library/provengo', model,
                    ignore=shutil.ignore_patterns('products', '.git', '.github', '.vscode', '__pycache__'))
    story_path = model / 'spec/js/lib_stories.js'
    if stories == 'business':
        story_path.write_text((HERE / 'business_stories_v013.js').read_text(encoding='utf-8'), encoding='utf-8')
    elif stories != 'full':
        raise ValueError('Unknown stories: ' + stories)
    story_path.write_text(set_counts(story_path.read_text(encoding='utf-8'), users, books), encoding='utf-8')

    dal_path = model / 'spec/js/dal.js'
    if profile == 'contract':
        dal_path.write_text(apply_contract(dal_path.read_text(encoding='utf-8'), loan_cap, hold_cap, pair_cap), encoding='utf-8')
    elif profile != 'original':
        raise ValueError('Unknown profile: ' + profile)

    interface = (model / 'spec/js/interfaces.library.js').read_text(encoding='utf-8')
    if 'requestOneOfDirect' in interface or 'data.model' in interface:
        raise RuntimeError('Expected the single-event interface layer (no requestOneOfDirect)')
    (model / 'data/v013_endpoint.js').write_text('var host = "' + host + '";\nvar port = ' + str(port) + ';\n', encoding='utf-8')
    with (model / 'config/provengo.yml').open('a', encoding='utf-8') as out:
        out.write('\n# v013 workload bound, not a server-side business restriction.\nscenario.max-length: ' + str(max_length) + '\n')

    shutil.copy2(repo / 'library/sut/sut_buggy_issta.py', root / 'sut_buggy_issta.py')
    contract = json.loads((repo / 'library/sut/library_openapi_issta.json').read_text(encoding='utf-8'))
    contract['servers'] = [{'url': 'http://' + host + ':' + str(port)}]
    write(root / 'openapi.json', contract)
    description = {'profile': profile, 'stories': stories, 'version': 'v013', 'users': users, 'books': books,
                   'interface': 'single-event (one REST request per action)',
                   'bounds': {'loan_cap': loan_cap, 'hold_cap': hold_cap, 'pair_cap': pair_cap, 'max_length': max_length} if profile == 'contract' else {'max_length': max_length},
                   'isolation': 'reset + empty public lists + fresh JVM per case'}
    write(root / 'model_profile.json', description)
    write(root / 'input_hashes.json', {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*')) if p.is_file()})
    return description
