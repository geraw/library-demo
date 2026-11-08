"""Causal maintenance candidates. Local development; no rarity qualification.
The original CRUD handlers own validation. Optional deferred indexes are maintained
by all indexed modes; each mutation changes one maintenance operation.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path
from flask import request, jsonify

ARMS = ['original', 'baseline', 'B1', 'B2', 'B3', 'B4', 'B5', 'B6']

def create(mode='baseline'):
    if mode not in ARMS: raise ValueError(mode)
    spec=importlib.util.spec_from_file_location('library_instance',Path(__file__).with_name('original.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    if mode=='original': return m.app
    app=m.app;views=dict(app.view_functions)
    st={}
    def reset():
        st.clear();st.update(tickets={},canceled={},blocked={},retired={},handoffs={},
            positions={},pins=set(),pending_repairs={},pairs={},pair_leases={},pair_forward={},cache={},catalog={},snapshots=[],deleted=set())
    reset()
    def number(v):
        if isinstance(v,bool):return None
        try:return int(v)
        except (ValueError,TypeError):return None
    def live_loan(u=None,b=None):
        return next((x for x in m.loans if (u is None or x['userId']==u) and (b is None or x['bookId']==b)),None)
    def book_holds(b):return [h for h in m.holds if h['bookId']==b]
    def crossed(u,b):
        """Return the other borrower/book in a two-sided reservation cycle."""
        for other in m.loans:
            v,y=other['userId'],other['bookId']
            if v!=u and y!=b and any(h['userId']==u and h['bookId']==y for h in m.holds) and any(h['userId']==v and h['bookId']==b for h in m.holds):
                return v,y
        return None
    def rebuild_positions():
        # A loan pins its borrower's hold handles only for a multi-book group.
        grouped={h['userId'] for h in m.holds if len({x['bookId'] for x in m.holds if x['userId']==h['userId']})>1}
        pinned={x['userId'] for x in m.loans}&grouped
        for i,h in enumerate(m.holds):
            if h['userId'] not in pinned:st['positions'][h['id']]=i
            else:st['positions'].setdefault(h['id'],i)
        st['pins']=pinned
    def cache_change(u,b):
        for key,entry in list(st['cache'].items()):
            if key[0] in (None,u) and key[1] in (None,b):
                if entry['leases']:
                    entry['dirty']=True
                    entry['refresh']=None
                else:st['cache'].pop(key,None)
    @app.before_request
    def indexed():
        ep=request.endpoint
        if ep not in views:return None
        args=request.view_args or {};body=request.get_json(silent=True)
        if not isinstance(body,dict):body={}
        u,b=number(body.get('userId')),number(body.get('bookId'))
        loans0,holds0=deepcopy(m.loans),deepcopy(m.holds)
        h=next((x for x in holds0 if x['id']==number(args.get('hold_id'))),None)
        removed=next((x for x in loans0 if x['userId']==number(args.get('user_id')) and x['bookId']==number(args.get('book_id'))),None)
        key=(number(request.args.get('userId')),number(request.args.get('bookId')))
        # Intercept only valid input after the original handler validates it below.
        if ep=='search_loans':
            response=app.make_response(views[ep](**args))
            if response.status_code>=400:return response
            entry=st['cache'].get(key)
            if entry and not entry['dirty']:return jsonify(deepcopy(entry['rows']))
            # Refresh is staged while its dependency leases are still live.
            if entry and entry['dirty']:
                entry['refresh']=deepcopy(response.get_json())
            # A dirty leased entry is bypassed, never used as an API snapshot.

            if not entry and key!=(None,None):
                candidate=live_loan(u=key[0],b=key[1])
                if candidate:
                    cross=crossed(candidate['userId'],candidate['bookId'])
                    if cross:
                        v,y=cross
                        leases={x['id'] for x in holds0 if (x['userId'],x['bookId']) in [(candidate['userId'],y),(v,candidate['bookId'])]}
                        st['cache'][key]={'rows':deepcopy(response.get_json()),'leases':leases,'dirty':False,'refresh':None}
            return response
        response=app.make_response(views[ep](**args));data=response.get_json(silent=True)
        if response.status_code>=400:return response
        if ep=='reset_database':
            reset();st['catalog']={x['id']:deepcopy(x) for x in m.books};rebuild_positions()
            st['pairs']={(x['userId'],x['bookId']):deepcopy(x) for x in m.loans}
        elif ep=='add_book':st['catalog'][data['id']]=deepcopy(data)
        elif ep=='add_loan':
            # The row was legally inserted; reject only the stale occupancy view.
            owner=st['blocked'].get(b)
            if mode=='B1' and owner is not None and live_loan(u=owner) and owner!=u:
                m.loans=loans0
                return jsonify(error='Book already has an active loan'),400
            ticket=st['tickets'].get(b)
            if ticket and ticket['next']==u:
                # B1 omits ownership transfer of a shared reservation ticket.
                if mode!='B1':ticket['owner']=u
                ticket['next']=None
                ticket['handed']=True
            retired=st['retired'].get(b)
            if retired and retired['userId']!=u:
                successor=live_loan(u=retired['userId'])
                if successor and successor['bookId']!=b:
                    st['handoffs'][b]={'retired':deepcopy(retired),'successor':deepcopy(successor),'borrower':u}
            # Record both independently rebound sides of a leased composite index.
            for pair0,forward in st['pair_forward'].items():
                if pair0[0]==u and pair0[1]!=b:forward['user_side']=b
                if pair0[1]==b and pair0[0]!=u:forward['book_side']=u
            pair=(u,b);old=st['pairs'].get(pair)
            lease=st['pair_leases'].get(pair,set())
            forward=st['pair_forward'].get(pair,{})
            rebound=forward.get('user_side') is not None and forward.get('book_side') is not None
            if mode!='B5' or not old or not lease or not rebound:
                st['pairs'][pair]=deepcopy(data)
            if u in st['pending_repairs']:
                # A new loan incarnation repins this owner's same handle region.
                st['pending_repairs'][u]['superseded']=True
            cache_change(u,b);rebuild_positions()
        elif ep=='add_hold':
            st['positions'][data['id']]=len(m.holds)-1
            loan=live_loan(b=b)
            waiting={x['userId'] for x in book_holds(b) if not loan or x['userId']!=loan['userId']}
            if loan and len(waiting)>1 and b not in st['tickets']:
                st['tickets'][b]={'owner':loan['userId'],'next':None,'holders':set(waiting),'handed':False}
            rebuild_positions()
        elif ep=='delete_loan' and removed:
            u,b=removed['userId'],removed['bookId'];pair=(u,b)
            # Keep retired descriptors only while reservations pin their lifetime.
            if book_holds(b):st['retired'][b]=deepcopy(removed)
            cross0=None
            for other in loans0:
                v,y=other['userId'],other['bookId']
                if v!=u and y!=b and any(x['userId']==u and x['bookId']==y for x in holds0) and any(x['userId']==v and x['bookId']==b for x in holds0):
                    cross0={(x['id']) for x in holds0 if (x['userId'],x['bookId']) in [(u,y),(v,b)]};break
            old=st['pairs'].get(pair)
            if mode=='B5' and old and old['id']!=removed['id']:
                m.loans=[x for x in loans0 if x['id']!=old['id']]
            if cross0:
                st['pair_leases'][pair]=cross0
                st['pair_forward'].setdefault(pair,{'user_side':None,'book_side':None})
            elif not st['pair_leases'].get(pair):st['pairs'].pop(pair,None)
            old_pins=set(st['pins'])
            stale={x['id']:st['positions'].get(x['id']) for x in m.holds if x['userId']==u and u in old_pins}
            rebuild_positions()
            if stale and st['pins']:
                # Another region is still pinned; enqueue the repair for final release.
                st['pending_repairs'].setdefault(u,{'loan_id':removed['id'],
                    'positions':{k:v for k,v in stale.items() if v is not None},'superseded':False})
            if not st['pins'] and st['pending_repairs']:
                if mode=='B3':
                    # Missing incarnation check lets an obsolete repair overwrite a repinned region.
                    for repair in st['pending_repairs'].values():
                        if repair['superseded']:st['positions'].update(repair['positions'])
                st['pending_repairs'].clear()
            cache_change(u,b)
            for book,owner in list(st['blocked'].items()):
                if owner==u:st['blocked'].pop(book)
        elif ep=='delete_hold' and h:
            u,b=h['userId'],h['bookId']
            pos=st['positions'].pop(h['id'],None)
            if mode=='B3' and u not in st['pins'] and pos is not None:
                m.holds=[x for i,x in enumerate(holds0) if i!=pos]
            ticket=st['tickets'].get(b)
            if ticket:
                if not live_loan(b=b) and book_holds(b):ticket['next']=u
                if not book_holds(b):
                    owner=ticket['owner']
                    if ticket['handed'] and live_loan(u=owner):st['blocked'][b]=owner
                    st['tickets'].pop(b)
            for pair,leases in list(st['pair_leases'].items()):
                leases.discard(h['id'])
                if not leases:
                    st['pair_leases'].pop(pair)
                    st['pair_forward'].pop(pair,None)
                    active=live_loan(u=pair[0],b=pair[1])
                    if active:st['pairs'][pair]=deepcopy(active)
                    else:st['pairs'].pop(pair,None)
            for k,entry in list(st['cache'].items()):
                entry['leases'].discard(h['id'])
                if not entry['leases'] and entry['dirty']:
                    if mode=='B4' and entry['refresh']:
                        # Positive refresh merged with setdefault: old pair incarnation wins.
                        entry['dirty']=False
                    else:st['cache'].pop(k)
            for snapshot in list(st['snapshots']):
                snapshot['leases'].discard(h['id'])
                if not snapshot['leases']:
                    for bid,row in snapshot['rows'].items():
                        if mode=='B6' or bid not in st['deleted']:st['catalog'][bid]=deepcopy(row)
                    st['snapshots'].remove(snapshot)
            rebuild_positions()
        elif ep=='delete_book':
            b=number(args['book_id']);st['deleted'].add(b);st['catalog'].pop(b,None)
            task=st['handoffs'].pop(b,None)
            if task and not book_holds(b):
                old=task['retired'];successor=task['successor'];active=live_loan(u=old['userId'])
                # Cascade task must be bound to the original book and incarnation.
                # Resolve a deferred retirement graph. Shared borrower descriptors can
                # form a cycle after different books hand off to different borrowers.
                visited={b};cursor=task;cycle=False
                while cursor:
                    next_book=cursor['successor']['bookId']
                    if next_book in visited:
                        cycle=True;break
                    visited.add(next_book)
                    successor_task=st['handoffs'].get(next_book)
                    if not successor_task or successor_task['retired']['id']!=cursor['successor']['id']:break
                    cursor=successor_task
                if mode=='B2' and cycle and active and active['id']==cursor['successor']['id']:
                    # Faulty cycle fallback cascades by the live borrower, not book.
                    m.loans=[x for x in m.loans if x['userId']!=old['userId']]
                    cache_change(old['userId'],active['bookId'])
            st['retired'].pop(b,None)
        elif ep=='search_books':
            # Deferred catalog materialization leases a page across two borrowed books.
            for holder in {x['userId'] for x in m.holds}:
                leases=[x for x in m.holds if x['userId']==holder and live_loan(b=x['bookId'])]
                borrowed={x['bookId'] for x in leases}
                if len(borrowed)>1:
                    ids={x['id'] for x in leases}
                    if not any(x['leases']==ids for x in st['snapshots']):
                        st['snapshots'].append({'leases':ids,'rows':{bid:deepcopy(st['catalog'][bid]) for bid in borrowed}})
            q=request.args.get('q','').lower()
            response=jsonify([deepcopy(x) for x in st['catalog'].values() if not q or q in str(x).lower()])
        return response
    return app

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=ARMS,default='baseline');p.add_argument('--port',type=int,default=23600)
    a=p.parse_args();create(a.mode).run(host='127.0.0.1',port=a.port,threaded=False)
