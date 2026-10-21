"""Offline evidence ingestion. No HTTP, generator execution or semantic verdicts."""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import zipfile
from collections import Counter
from gateways import select

VERSION = 'natchan-evidence/1'


@dataclass(frozen=True)
class Limits:
    max_members: int = 10000
    max_member_bytes: int = 32 * 1024 * 1024
    max_total_bytes: int = 256 * 1024 * 1024
    max_depth: int = 2
    max_events: int = 100000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def decode(data):
    """Reuse Vikunja schedule reader's BOM and BOMless PowerShell UTF16 handling."""
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        return data.decode('utf-16'), 'utf-16'
    sample = data[:4096]
    if sample and sample.count(b'\x00') > len(sample) // 8:
        return data.decode('utf-16-le'), 'utf-16-le'
    return data.decode('utf-8-sig'), 'utf-8-sig'


class Inventory:
    def __init__(self, path, limits=None):
        self.path = Path(path)
        self.limits = limits or Limits()
        self.artifacts = []
        self.issues = []
        self.data = {}
        self.total = 0
        self.seen = 0
        self.root_sha256 = None

    def issue(self, code, source=None, detail=None):
        self.issues.append(dict(code=code, source=source, detail=detail))

    def add(self, locator, data, status='available'):
        artifact = dict(id='a' + str(len(self.artifacts) + 1), locator=locator,
                        status=status, byte_count=len(data) if data is not None else None,
                        sha256=sha(data) if data is not None else None)
        self.artifacts.append(artifact)
        if data is not None:
            self.data[locator] = data
        return artifact

    def scan(self):
        # Stream the root hash; never load a whole outer ZIP just to fingerprint it.
        h = hashlib.sha256()
        with self.path.open('rb') as source:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                h.update(block)
        self.root_sha256 = h.hexdigest()
        try:
            with zipfile.ZipFile(self.path) as z:
                self.walk(z, '', 0)
        except (zipfile.BadZipFile, OSError) as exc:
            self.issue('invalid_archive', detail=str(exc))
        return self

    def walk(self, z, prefix, depth):
        names = [i.filename for i in z.infolist() if not i.is_dir()]
        duplicates = {n for n, count in Counter(names).items() if count > 1}
        for info in z.infolist():
            if info.is_dir():
                continue
            self.seen += 1
            if self.seen > self.limits.max_members:
                self.issue('member_limit', prefix or None)
                return
            name = info.filename.replace('\\', '/')
            locator = prefix + name
            if (name.startswith('/') or ':' in name or '!' in name or
                    '..' in PurePosixPath(name).parts):
                self.add(locator, None, 'rejected')
                self.issue('unsafe_member_name', locator)
                continue
            if info.filename in duplicates or locator in self.data:
                self.add(locator, None, 'ambiguous')
                self.issue('duplicate_member', locator)
                continue
            if info.file_size > self.limits.max_member_bytes:
                self.add(locator, None, 'limited')
                self.issue('member_size_limit', locator)
                continue
            if self.total + info.file_size > self.limits.max_total_bytes:
                self.add(locator, None, 'limited')
                self.issue('total_size_limit', locator)
                continue
            try:
                with z.open(info) as source:
                    data = source.read(self.limits.max_member_bytes + 1)
                if len(data) != info.file_size or len(data) > self.limits.max_member_bytes:
                    raise ValueError('Member size differs from declared size or limit')
            except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, NotImplementedError) as exc:
                self.add(locator, None, 'invalid')
                self.issue('member_read_failed', locator, str(exc))
                continue
            self.total += len(data)
            self.add(locator, data)
            if name.lower().endswith('.zip'):
                if depth >= self.limits.max_depth:
                    self.issue('nested_depth_limit', locator)
                else:
                    try:
                        with zipfile.ZipFile(io.BytesIO(data)) as nested:
                            self.walk(nested, locator + '!/', depth + 1)
                    except zipfile.BadZipFile as exc:
                        self.issue('invalid_nested_archive', locator, str(exc))


def library_manifest():
    """Reuse v001's explicit three-arm layout; labels are adapter declarations."""
    return dict(schema_version=1, runs=[dict(id=arm, tool='provengo', system='library',
        variant=variant, tool_gateway='provengo-fixed-java-v011', product_gateway='library-issta-v006', artifacts={'trace':arm + '/http.jsonl',
        'native_jsonl':arm + '/native.jsonl', 'execution_json':arm + '/java-suite-execution.json'})
        for arm, variant in [('control', 'healthy'), ('business-four', 'bugs-1-2-3-5'),
                             ('book-read-one', 'bug-4')]])


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get('schema_version') != 1 or not isinstance(manifest.get('runs'), list):
        raise ValueError('Expected v001-compatible schema_version 1 and runs array')
    ids = set()
    for run in manifest['runs']:
        if not isinstance(run, dict) or any(not isinstance(run.get(k), str) or not run[k] for k in ('id', 'tool', 'system')):
            raise ValueError('Every run requires nonempty id, tool and system')
        if run['id'] in ids:
            raise ValueError('Duplicate run id')
        ids.add(run['id'])
        select(run)
        if not isinstance(run.get('artifacts', {}), dict) or any(not isinstance(v, str) or not v for v in run.get('artifacts', {}).values()):
            raise ValueError('artifacts must map labels to exact archive member locators')


def ingest(path, manifest=None, limits=None, library=False):
    if library and manifest is not None:
        raise ValueError('Choose library adapter or manifest')
    limits = limits or Limits()
    manifest = library_manifest() if library else manifest
    if manifest is not None:
        validate_manifest(manifest)
    inv = Inventory(path, limits).scan()
    artifacts = {a['locator']:a for a in inv.artifacts if a['status'] == 'available'}
    report = dict(schema_version=VERSION, source=dict(filename=Path(path).name, sha256=inv.root_sha256),
                  status='complete', artifacts=inv.artifacts, runs=[], events=[], findings=[], issues=inv.issues,
                  capabilities=dict(semantic_evaluation=False, native_detection=False, offline_only=True))
    if manifest is None:
        report['issues'].append(dict(code='no_run_mapping', source=None, detail='Inventory only; supply a manifest or supported adapter'))
    for declaration in (manifest or {}).get('runs', []):
        tool_gateway, product_gateway = select(declaration)
        run = dict(tool_gateway=tool_gateway.id, product_gateway=product_gateway.id, id=declaration['id'], tool=declaration['tool'], product=declaration['system'],
                   variant=declaration.get('variant'), status='complete', artifacts={},
                   metadata={k:v for k,v in declaration.items() if k not in ('id','tool','system','variant','artifacts')})
        report['runs'].append(run)
        for label, locator in declaration.get('artifacts', {}).items():
            artifact = artifacts.get(locator)
            if artifact is None:
                run['artifacts'][label] = None
                inv.issue('missing_or_unavailable_artifact', locator, dict(run_id=run['id'], label=label))
                run['status'] = 'incomplete'
                continue
            run['artifacts'][label] = artifact['id']
            if label not in ('trace', 'native_jsonl', 'execution_json'):
                continue  # Preserve unknown formats without pretending to understand them.
            try:
                text, encoding = decode(inv.data[locator])
                artifact['encoding'] = encoding
            except UnicodeError as exc:
                inv.issue('invalid_encoding', locator, str(exc)); run['status'] = 'incomplete'
                continue
            lines = [(None, text)] if label == 'execution_json' else enumerate(text.splitlines(), 1)
            current_case = None
            count_before = len(report['events'])
            for number, line in lines:
                if not line.strip():
                    continue
                if len(report['events']) >= limits.max_events:
                    inv.issue('event_limit', locator); run['status'] = 'incomplete'
                    break
                try:
                    payload = json.loads(line)
                    if not isinstance(payload, dict):
                        raise ValueError('Expected JSON object')
                except ValueError as exc:
                    inv.issue('invalid_record', locator, dict(line=number, error=str(exc)))
                    run['status'] = 'incomplete'
                    # Never carry a verified boundary across an unreadable trace record.
                    if label == 'trace':
                        current_case = None
                    continue
                role = payload.get('role')
                if label == 'trace' and role == 'boundary':
                    current_case = payload.get('case')
                declared_case = payload.get('case')
                case_id = declared_case if declared_case is not None else current_case
                scope = 'unknown'
                if label == 'trace' and current_case is not None:
                    scope = 'recorded_boundary' if declared_case in (None, current_case) else 'conflicting'
                elif label == 'native_jsonl' and declared_case is not None:
                    scope = 'record_declared'
                if scope == 'conflicting':
                    inv.issue('conflicting_case_scope', locator, dict(line=number, run_id=run['id']))
                    run['status'] = 'incomplete'
                    current_case = None
                # Preserve imported verdicts as claims, never recompute or endorse them here.
                normalized = tool_gateway.normalize(label, payload)
                report['events'].append(dict(id='e' + str(len(report['events']) + 1), run_id=run['id'],
                    **normalized, product=product_gateway.describe(payload), scope=dict(case_id=case_id, basis=scope),
                    source=dict(artifact_id=artifact['id'], line=number), payload=payload))
            if len(report['events']) == count_before:
                inv.issue('empty_or_unreadable_artifact', locator, dict(run_id=run['id'], label=label))
                run['status'] = 'incomplete'
    if library:
        try:
            completed = json.loads(decode(inv.data['completed.json'])[0])
            expected = completed.get('scenario_count')
            if completed.get('complete') is not True or type(expected) is not int or expected < 0:
                raise ValueError('Invalid completion metadata')
            for run in report['runs']:
                cases = [e['payload'].get('case') for e in report['events'] if e['run_id'] == run['id'] and e['kind'] == 'native_record']
                if len(cases) != expected or len(set(cases)) != expected or any(c is None for c in cases):
                    run['status'] = 'incomplete'
                    inv.issue('native_case_count_mismatch', detail=dict(run_id=run['id'], expected=expected, observed=len(cases)))
        except (KeyError, ValueError, TypeError) as exc:
            inv.issue('invalid_completion_metadata', 'completed.json', str(exc))
            for run in report['runs']:
                run['status'] = 'incomplete'
    if manifest is not None and not report['runs']:
        inv.issue('no_runs_declared')
    if inv.issues or any(r['status'] != 'complete' for r in report['runs']):
        report['status'] = 'incomplete'
    report['summary'] = dict(run_count=len(report['runs']), artifact_count=len(report['artifacts']),
                           event_count=len(report['events']), issue_count=len(report['issues']),
                           finding_count=None, note='Ingestion only. No findings were evaluated.')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--manifest', type=Path)
    group.add_argument('--library-v011', action='store_true')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig')) if args.manifest else None
    report = ingest(args.archive, manifest, library=args.library_v011)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
        target.write('\n')
    print('NATCHAN_EVIDENCE ' + str(args.output.resolve()))
    print('NATCHAN_INGESTION ' + report['status'].upper())
    return 0 if report['status'] == 'complete' else 2


if __name__ == '__main__':
    raise SystemExit(main())
