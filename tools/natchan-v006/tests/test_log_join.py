from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from log_join import join,error_family


def fixture():
    rows=[];lines=[];start=datetime(2026,10,21,15,0,0,tzinfo=timezone.utc)
    for i in range(12):
        t=start+timedelta(seconds=i)
        rows.append(dict(category='research',method='GET',path=f'/items/{i}',status=200,t_utc=t.isoformat()))
        lines.append((t+timedelta(hours=3)).strftime('%Y/%m/%d %H:%M:%S')+f' HTTPRequest completed GET /api/v1/items/{i} for host, 200 OK @ repo/file.go:1(repo.Get)')
    for i in range(2):
        t=start+timedelta(seconds=20,milliseconds=i*200)
        rows.append(dict(category='research',method='POST',path='/releases',status=500,t_utc=t.isoformat()))
        prefix=(t+timedelta(hours=3)).strftime('%Y/%m/%d %H:%M:%S')
        lines.append(prefix+' release.go:1:CreateRelease() [E] release tag name is not valid')
        lines.append(prefix+' HTTPRequest completed POST /api/v1/releases for host, 500 Internal Server Error @ repo/file.go:1(repo.CreateRelease)')
    return rows,lines


class LogJoinTests(unittest.TestCase):
    def test_calibrates_from_nonerror_anchors_and_joins_repeated_key(self):
        rows,lines=fixture();links,cal=join(rows,'\n'.join(lines),True)
        self.assertEqual(len(links),2);self.assertEqual(cal['clock_offset_seconds'],10800)
        self.assertEqual(cal['anchor_count'],12)

    def test_repeated_keys_require_complete_sequential_provenance(self):
        rows,lines=fixture();links,cal=join(rows,'\n'.join(lines))
        self.assertEqual(links,{})

    def test_background_error_is_not_request_handler_error(self):
        rows,lines=fixture()
        lines.insert(-1,'2026/10/21 18:00:20 notify.go:1:handler() [E] database is locked')
        links,cal=join(rows,'\n'.join(lines),True)
        self.assertEqual(len(links),2)
        self.assertTrue(all('release tag name' in x['message'] for x in links.values()))

    def test_missing_completion_is_not_filled(self):
        rows,lines=fixture();lines.pop();links,cal=join(rows,'\n'.join(lines),True)
        self.assertEqual(links,{})

    def test_nonmonotonic_client_order_is_rejected(self):
        rows,lines=fixture();rows[-2],rows[-1]=rows[-1],rows[-2]
        self.assertEqual(join(rows,'\n'.join(lines),True)[0],{})

    def test_git_ref_failure_is_not_database_lock(self):
        self.assertEqual(error_family("cannot lock ref 'refs/tags/LLLL'"),'git_ref_failure')
        self.assertEqual(error_family('database is locked'),'other')


if __name__=='__main__':unittest.main()
