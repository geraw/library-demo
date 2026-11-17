"""Frozen StrictGuidedRun copy for the single-event model.

Applies the same four v011 execution edits (native RTV evaluation, ActuationSummary checks,
stop on failed actuation, per-scenario runtime cleanup) plus TWO matching edits: the runner's
chooserName() falls back to V013Match.actionName() instead of the bare HTTP verb, so the
catalog's existing name matching ("<action> (valid): <ids>", never a nonexistent 10-digit id)
works for events that carry no data.model any more; and a step whose action starts with
"reject" may target a 4xx-expecting event (a business-rule rejection check as a scenario step).

Scenario definitions and the selection strategy are never modified; the catalog section of the
source is checked byte-for-byte.
"""
import hashlib

SOURCE_SHA = '04084199740dedaeacade4efb4310ec8525181ae2de6b8a6376887146b85f514'

RUNTIME_EDITS = [
    ('                for (Actuator a : actuators) {',
     '                BEvent concrete;\n'
     '                try { concrete = V011Actuation.evaluate(event); }\n'
     '                catch (Exception ex) { System.out.println("[actuate exception] RTV: " + ex); runner.halt(); return; }\n'
     '                for (Actuator a : actuators) {'),
    ('                        a.actuate(bp, event);',
     '                        V011Actuation.actuate(a, bp, concrete);'),
    ('                        System.out.println("      [actuate exception] " + ex);',
     '                        System.out.println("      [actuate exception] " + ex);\n'
     '                        runner.halt(); return;'),
    ('        runner.run();',
     '        V011Actuation.begin(program);\n'
     '        try { runner.run(); } finally { V011Actuation.end(actuators); }'),
]

MATCHING_EDITS = [
    ('        return event.getName();',
     '        return V013Match.actionName(event);'),
    # A step whose action is a rejection check ("rejectDeleteUser400") targets an event that
    # expects 4xx; expectsRejection() must not veto it. Success steps keep the veto.
    ('        return chooserNameMatches(chooserName(event), step.action)\n'
     '                && !expectsRejection(event)',
     '        return chooserNameMatches(chooserName(event), step.action)\n'
     '                && (step.action.startsWith("reject") || !expectsRejection(event))'),
]

CATALOG_BOUNDARY = '    // Matching\n'


def normalized(source):
    return source.replace('\r\n', '\n').rstrip('\n')


def patch(source):
    source = normalized(source)
    if hashlib.sha256(source.encode()).hexdigest() != SOURCE_SHA:
        raise RuntimeError('Unexpected fixed Java source')
    original = source
    for old, new in RUNTIME_EDITS + MATCHING_EDITS:
        if source.count(old) != 1:
            raise RuntimeError('Patch anchor changed: ' + old)
        source = source.replace(old, new)
    if source.count(CATALOG_BOUNDARY) != 1:
        raise RuntimeError('Catalog boundary changed')
    if source.split(CATALOG_BOUNDARY)[0] != original.split(CATALOG_BOUNDARY)[0]:
        raise RuntimeError('Scenario catalog changed')
    return source + '\n'
