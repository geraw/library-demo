"""Indexed Library variant. Each named mode mutates one maintenance operation.
These are candidate faults, not empirically calibrated rare defects.
"""
import importlib.util
from pathlib import Path
from copy import deepcopy
from flask import request, jsonify


def create(mode='baseline'):
    if mode not in ['original', 'baseline', 'B1', 'B2', 'B3', 'B4', 'B5', 'B6']:
        raise ValueError(mode)
    spec = importlib.util.spec_from_file_location('library_instance', Path(__file__).with_name('original.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if mode == 'original':
        return m.app
    app = m.app
    views = dict(app.view_functions)
    state = {}
    def reset_state():
        state.clear()
        state.update(owners={}, reservation_owner={}, blocked={}, retired={},
                     positions={}, pairs={}, cache={}, book_index={})
    reset_state()

    @app.before_request
    def indexed_request():
        endpoint = request.endpoint
        if endpoint not in views:
            return None
        args = request.view_args or {}
        body = request.get_json(silent=True) or {}
        before_loans, before_holds = deepcopy(m.loans), deepcopy(m.holds)
        before_books = deepcopy(m.books)
        def numeric(value):
            try: return int(value)
            except (ValueError, TypeError): return None
        u, b = numeric(body.get('userId')), numeric(body.get('bookId'))
        if endpoint == 'add_loan' and mode == 'B1' and b in state['blocked']:
            owner = state['blocked'][b]
            if any(x['userId'] == owner for x in m.loans) and any(x['id'] == u for x in m.users):
                return jsonify(error='Book already has an active loan'), 400
        # A query cache is an actual read path, not a history-pattern recognizer.
        key = (request.args.get('userId'), request.args.get('bookId'))
        if endpoint == 'search_loans' and key != (None, None) and key in state['cache']:
            return jsonify(deepcopy(state['cache'][key]))
        target_hold = next((h for h in before_holds if h['id'] == numeric(args.get('hold_id'))), None)
        indexed_loan = state['pairs'].get((numeric(args.get('user_id')), numeric(args.get('book_id'))))
        response = app.make_response(views[endpoint](**args))
        data = response.get_json(silent=True)
        if response.status_code >= 400:
            return response
        if endpoint == 'reset_database':
            reset_state()
            state['book_index'] = {x['id']:deepcopy(x) for x in m.books}
            state['positions'] = {h['id']:i for i,h in enumerate(m.holds)}
            state['pairs'] = {(x['userId'],x['bookId']):deepcopy(x) for x in m.loans}
        elif endpoint == 'add_book':
            state['book_index'][data['id']] = deepcopy(data)
        elif endpoint == 'add_loan':
            previous = state['owners'].get(b)
            state['owners'][b] = u
            # B5: setdefault preserves the retired incarnation of a composite key.
            if mode == 'B5': state['pairs'].setdefault((u,b), deepcopy(data))
            else: state['pairs'][(u,b)] = deepcopy(data)
            state['cache'].clear()
            # Correct reservation ownership follows the new borrower.
            if mode != 'B1' or b not in state['reservation_owner']:
                state['reservation_owner'][b] = u
        elif endpoint == 'add_hold':
            state['positions'][data['id']] = len(m.holds)-1
            owner = next((x['userId'] for x in m.loans if x['bookId']==b), None)
            if owner is not None: state['reservation_owner'].setdefault(b, owner)
        elif endpoint == 'delete_loan':
            u, b = numeric(args['user_id']), numeric(args['book_id'])
            removed = next(x for x in before_loans if x['userId']==u and x['bookId']==b)
            if mode == 'B2': state['retired'].setdefault(b, deepcopy(removed))
            else: state['retired'][b] = deepcopy(removed)
            if mode == 'B5' and indexed_loan and indexed_loan['id'] != removed['id']:
                # Repository deletes the stale indexed id; the current row survives.
                m.loans = [x for x in before_loans if x['id'] != indexed_loan['id']]
            if mode != 'B5': state['pairs'].pop((u,b), None)
            if mode != 'B4': state['cache'].clear()
            for book, owner in list(state['blocked'].items()):
                if owner == u: state['blocked'].pop(book)
        elif endpoint == 'delete_hold' and target_hold:
            h = target_hold
            pos = state['positions'].pop(h['id'], None)
            if mode == 'B3' and pos is not None:
                # Missing reindex after prior erasure makes this position stale.
                m.holds = [x for i,x in enumerate(before_holds) if i != pos]
            if mode != 'B3': state['positions'] = {x['id']:i for i,x in enumerate(m.holds)}
            if not any(x['bookId']==h['bookId'] for x in m.holds):
                owner = state['reservation_owner'].pop(h['bookId'], None)
                if owner is not None and any(x['userId']==owner and x['bookId']!=h['bookId'] for x in m.loans):
                    state['blocked'][h['bookId']] = owner
        elif endpoint == 'delete_book':
            b = numeric(args['book_id'])
            retired = state['retired'].get(b)
            if mode == 'B2' and retired:
                # Wrong cascade key: userId instead of bookId, from retired relation.
                m.loans = [x for x in m.loans if x['userId'] != retired['userId']]
                state['cache'].clear()
            if mode != 'B6' or not retired:
                state['book_index'].pop(b, None)
            state['retired'].pop(b, None)
        elif endpoint == 'search_loans' and key != (None,None):
            state['cache'][key] = deepcopy(data)
        elif endpoint == 'search_books':
            q = request.args.get('q','').lower()
            response = jsonify([deepcopy(x) for x in state['book_index'].values() if not q or q in str(x).lower()])
        return response
    return app

if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--mode',default='baseline');p.add_argument('--port',type=int,default=23600)
    a=p.parse_args();create(a.mode).run(host='127.0.0.1',port=a.port,threaded=False)
