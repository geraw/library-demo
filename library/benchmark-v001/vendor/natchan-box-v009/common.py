"""Deterministic files and explicit errors for the contract-only v009 development track."""
import hashlib
import json
import math
from pathlib import Path

VERSION = '009-dev.6'
ROOT = Path(__file__).resolve().parent


class InputError(ValueError):
    code = 2


class Unsupported(InputError):
    code = 3


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True,
                       allow_nan=False, indent=2) + '\n').encode('utf-8')


def pairs(items):
    out = {}
    for k, v in items:
        if k in out:
            raise InputError('DUPLICATE_JSON_KEY')
        out[k] = v
    return out


def loads(raw):
    def finite(value):
        number = float(value)
        if not math.isfinite(number):
            raise InputError('NONFINITE_JSON_NUMBER')
        return number
    try:
        result = json.loads(raw, object_pairs_hook=pairs,
                            parse_float=finite,
                            parse_constant=lambda _: (_ for _ in ()).throw(InputError('NONFINITE_JSON_NUMBER')))
        stack = [(result, 0)]
        while stack:
            value, depth = stack.pop()
            if depth > 128:
                raise InputError('JSON_DEPTH_LIMIT')
            if isinstance(value, dict):
                stack.extend((v, depth + 1) for v in value.values())
            elif isinstance(value, list):
                stack.extend((v, depth + 1) for v in value)
        return result
    except (ValueError, UnicodeError, RecursionError) as e:
        raise InputError('INVALID_JSON') from e


def read(path, limit=32 * 1024 * 1024):
    try:
        with Path(path).open('rb') as f:
            raw = f.read(limit + 1)
    except OSError as e:
        raise InputError('INPUT_UNREADABLE') from e
    if len(raw) > limit:
        raise Unsupported('INPUT_SIZE_LIMIT')
    return raw


def write(path, value):
    Path(path).write_bytes(canonical(value))


def keys(value, allowed, required=()):
    if not isinstance(value, dict):
        raise InputError('OBJECT_REQUIRED')
    if set(value) - set(allowed):
        raise InputError('UNKNOWN_CONFIGURATION_FIELD')
    if set(required) - set(value):
        raise InputError('REQUIRED_CONFIGURATION_FIELD_MISSING')


def engine_hashes():
    # v009's independent route imports no earlier analyzer module or product catalog.
    return {p.name: digest(p.read_bytes()) for p in sorted(ROOT.glob('*.py'))}
