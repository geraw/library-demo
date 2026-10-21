"""Offline tool gateways. No SUT calls; original verdicts never become verified facts."""
import hashlib
import json
from pathlib import Path
import zipfile


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def parsed(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


def source(path, raw, member=None, record=None):
    result = {'file': str(path), 'sha256': digest(raw)}
    if member:
        result['member'] = member
    if record is not None:
        result['record'] = record
    return result


def load_gateway(path):
    """Read a retained gateway archive; reject ambiguous/oversized members."""
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate ZIP members')
        required = ['gateway-journal.jsonl', 'generated/contract-ir.json']
        if not all(n in names for n in required):
            raise ValueError('Missing gateway journal or IR')
        for info in archive.infolist():
            if info.file_size > 64 * 1024 * 1024:
                raise ValueError('ZIP member exceeds 64 MiB')
        raw = archive.read(required[0])
        records = [json.loads(line) for line in raw.decode('utf-8-sig').splitlines() if line.strip()]
        result_names = [n for n in names if n.startswith('result_') and n.endswith('.json')]
        if len(result_names) != 1:
            raise ValueError('Expected exactly one native result')
        return {'records': records, 'source': source(path, raw, required[0]),
                'archive_sha256': digest(path.read_bytes()),
                'ir': json.loads(archive.read(required[1])),
                'native': json.loads(archive.read(result_names[0])),
                'sut_log': archive.read('sut.log').decode('utf-8-sig') if 'sut.log' in names else '',
                'native_log_sha256': digest(archive.read('native.log')) if 'native.log' in names else None,
                'tool': 'provengo', 'format': 'research-gateway-jsonl/1'}


def load_transcript(path):
    path = Path(path)
    raw = path.read_bytes()
    document = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(document.get('transcript'), list):
        raise ValueError('A raw HTTP transcript is required; a result summary is insufficient')
    return {'records': document['transcript'], 'source': source(path, raw),
            'tool': 'direct-reproducer', 'format': 'http-transcript/1'}


def load_original_oracles(path):
    path = Path(path)
    raw = path.read_bytes()
    return {'records': [json.loads(s) for s in raw.decode('utf-8-sig').splitlines() if s.strip()],
            'source': source(path,raw), 'tool':'route-harness', 'format':'original-oracle-jsonl/1'}
