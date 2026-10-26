"""Explicit transport contract for unsupported toolkit input; not an engine-error fallback."""
class UnsupportedEvidence(ValueError): pass
class InvalidEvidence(ValueError): pass


def text(raw):
    if raw.startswith((b'\xff\xfe',b'\xfe\xff')):return raw.decode('utf-16')
    return raw.decode('utf-8-sig')

