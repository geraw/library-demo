"""Join complete route-harness HTTP journals to original Gitea server logs."""
from collections import defaultdict
from datetime import datetime,timezone
import re
import statistics

PATTERN=re.compile(r'^(\d{4}/\d\d/\d\d \d\d:\d\d:\d\d).*completed (\w+) /api/v1(\S+) .*?, (\d{3}) ')


def completions(text):
    lines=text.splitlines();result=[]
    for i,line in enumerate(lines):
        m=PATTERN.search(line)
        if not m:continue
        dt=datetime.strptime(m[1],'%Y/%m/%d %H:%M:%S').replace(tzinfo=timezone.utc)
        errors=[]
        handler=re.search(r'\((?:[^()]+\.)?(\w+)\)\s*$',line)
        for j in range(i-1,max(-1,i-6),-1):
            if 'completed ' in lines[j]:break
            if '[E]' in lines[j] and (not handler or re.search(r':'+re.escape(handler[1])+r'\(\)\s+\[E\]',lines[j])):
                errors.append((j+1,lines[j]))
        result.append(dict(key=(m[2],m[3],int(m[4])),timestamp=dt.timestamp(),line=i+1,errors=errors))
    return result


def join(records,text,complete_sequential=False):
    client=defaultdict(list);server=defaultdict(list)
    for i,r in enumerate(records):
        if r.get('category')!='research' or type(r.get('status')) is not int or not r.get('t_utc'):continue
        client[(r.get('method'),r.get('path'),r['status'])].append((i,datetime.fromisoformat(r['t_utc']).timestamp()))
    for c in completions(text):server[c['key']].append(c)
    # Calibrate only against uniquely identified NON-error calls. Never choose an
    # offset to force a known-bug signature match.
    anchors=[]
    for key,values in client.items():
        if key[2]>=500 or len(values)!=1 or len(server[key])!=1:continue
        anchors.append(server[key][0]['timestamp']-values[0][1])
    if len(anchors)<10:return {},{'status':'insufficient_clock_anchors','anchors':len(anchors)}
    center=statistics.median(anchors)
    offset=round(center/900)*900
    good=[d for d in anchors if abs(d-offset)<=2]
    if len(good)/len(anchors)<0.95:return {},{'status':'inconsistent_clock_anchors','anchors':len(anchors)}
    links={};ambiguous=[]
    for key,values in client.items():
        if not 500<=key[2]<=599:continue
        matches=server[key]
        if len(values)!=len(matches) or not values:
            ambiguous.append({'key':key,'reason':'different request/completion counts'});continue
        if len(values)>1 and not complete_sequential:
            ambiguous.append({'key':key,'reason':'repeated key needs explicit complete-sequential provenance'});continue
        # A complete sequential harness has one order-preserving bijection for
        # repeated method/path/status keys. One-second logs can have tied times;
        # their original line order disambiguates them.
        ordered=all(a[1]<b[1] for a,b in zip(values,values[1:]))
        bounded=all(abs(s['timestamp']-offset-c[1])<=2 for c,s in zip(values,matches))
        if not ordered or not bounded:
            ambiguous.append({'key':key,'reason':'nonmonotonic or inconsistent ordering/time'});continue
        for (i,when),s in zip(values,matches):
            if len(s['errors'])!=1:
                ambiguous.append({'record':i,'reason':'missing/ambiguous adjacent error'});continue
            links[i]={'message':s['errors'][0][1],'error_line':s['errors'][0][0],
                      'completion_line':s['line'],'clock_offset_seconds':offset,
                      'basis':'complete sequential harness; unique order-preserving method/path/status join; calibrated clock residual <=2s'}
    return links,{'status':'calibrated','clock_offset_seconds':offset,'anchor_count':len(anchors),
                  'inlier_count':len(good),'maximum_inlier_residual_seconds':max(abs(d-offset) for d in good),
                  'unresolved':ambiguous,'clock_offset_is_measured_not_assumed_timezone':True}


def error_family(message):
    tests=[('missing_assignee',r'user does not exist|user redirect does not exist'),
           ('missing_milestone',r'milestone does not exist'),('missing_git_object',r'object does not exist'),
           ('invalid_tag',r'release tag name is not valid'),('git_argument_nul',r'fork/exec .*git: invalid argument'),
           ('parse_integer',r'strconv\.ParseInt')]
    tests.append(('git_ref_failure',r"cannot lock ref 'refs/tags/"))
    return next((name for name,pattern in tests if re.search(pattern,message,re.I)),'other')
