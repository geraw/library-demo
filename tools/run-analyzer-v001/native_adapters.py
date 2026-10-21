"""Read tool-native artifacts. Counts retain their tool-specific meaning."""
import hashlib
import json
from pathlib import Path
import re


def fingerprint(path):return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
def unknown(reason):return {'status':'unknown','count':None,'metric':None,'reason':reason,'evidence':[]}
def read_log(path):return re.sub(r'\x1b\[[0-9;]*m','',path.read_text(encoding='utf-8-sig',errors='replace'))


def declared(path):
    value=json.loads(path.read_text(encoding='utf-8-sig'))
    count=value.get('count');metric=value.get('metric')
    if type(count) is not int or count<0 or not isinstance(metric,str) or not metric:
        raise ValueError('Declared native report requires nonnegative integer count and a metric')
    return {'status':'reported','count':count,'metric':metric,'evidence':[fingerprint(path)],
            'note':'Previously collected native metric; not independently reconstructed','original':value}


def provengo(artifacts):
    path=artifacts.get('native_jsonl')
    if path:
        rows=[];errors=[];ids=set()
        for line,text in enumerate(path.read_text(encoding='utf-8-sig').splitlines(),1):
            if not text.strip():continue
            try:
                row=json.loads(text)
                if type(row.get('native_pass')) is not bool:raise ValueError('Missing boolean native_pass')
                if row.get('case') is None:raise ValueError('Missing case identifier')
                key=str(row['case'])
                if key in ids:raise ValueError('Duplicate case identifier')
                ids.add(key);rows.append(row)
            except (ValueError,TypeError,AttributeError) as exc:errors.append({'line':line,'error':str(exc)})
        if not rows:return unknown('No native case results')
        failed=[str(r['case']) for r in rows if not r['native_pass']]
        return {'status':'incomplete' if errors else 'reported','count':None if errors else len(failed),
                'metric':'failed_fixed_test_cases','failed_cases':failed,'passed_cases':[str(r['case']) for r in rows if r['native_pass']],'case_count':len(rows),'issues':errors,
                'evidence':[fingerprint(path)],'note':'Failed tests, not distinct business bugs'}
    path=artifacts.get('log')
    if not path:return unknown('No Provengo native case report or log')
    mentions=[{'line':i,'text':line[:500]} for i,line in enumerate(read_log(path).splitlines(),1)
              if re.search(r'\bFAIL(?:ED)?\b|AssertionFail|\[actuate exception\]',line,re.I)]
    return {'status':'diagnostic_only','count':len(mentions),'metric':'native_failure_log_mentions',
            'mentions':mentions,'evidence':[fingerprint(path)],
            'note':'Historical fallback metric: log mentions are neither unique failed tests nor distinct bugs'}


def evomaster(artifacts):
    path=artifacts.get('log')
    if not path:return unknown('No EvoMaster native log')
    hits=re.findall(r'(?:Potential\s+faults|potentialFaults)\s*[:=]\s*(\d+)',read_log(path),re.I)
    if not hits:return unknown('No explicit potential-fault count found; absence is not zero')
    return {'status':'reported','count':int(hits[-1]),'metric':'potential_faults','evidence':[fingerprint(path)],
            'note':'Tool-reported potential faults, not externally confirmed business bugs'}


def restler(artifacts):
    folder=artifacts.get('bug_buckets')
    if not folder or not folder.is_dir():return unknown('No explicitly selected RESTler bug_buckets directory')
    if folder.name.lower()!='bug_buckets':raise ValueError('Select the exact bug_buckets directory, not a whole multi-run tree')
    files=sorted(p for p in folder.rglob('*') if p.is_file())
    if not files:return unknown('Empty bucket directory does not establish a completed zero-fault run')
    return {'status':'reported','count':len(files),'metric':'bug_bucket_files',
            'evidence':[fingerprint(p) for p in files],
            'note':'Historical artifact-file count, including any auxiliary files; not a deduplicated bug count'}


# Extension point for future generators: add an adapter without editing product rules.
ADAPTERS={'provengo':provengo,'restler':restler,'evomaster':evomaster}


def analyze(tool,artifacts):
    if tool not in ADAPTERS:return unknown('No native adapter registered for '+tool)
    try:
        if artifacts.get('native_json'):return declared(artifacts['native_json'])
        return ADAPTERS[tool](artifacts)
    except (OSError,ValueError,TypeError) as exc:
        result=unknown(str(exc));result['status']='invalid_artifact';return result
