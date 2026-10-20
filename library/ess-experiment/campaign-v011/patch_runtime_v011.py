"""Patch only execution plumbing in a frozen copy; never modify scenario definitions."""
import hashlib
SOURCE_SHA='04084199740dedaeacade4efb4310ec8525181ae2de6b8a6376887146b85f514'

def patch(source):
    source=source.replace('\r\n','\n').rstrip('\n')
    if hashlib.sha256(source.encode()).hexdigest()!=SOURCE_SHA:raise RuntimeError('Unexpected fixed Java source')
    original=source
    edits=[
        ('                for (Actuator a : actuators) {','                BEvent concrete;\n                try { concrete = V011Actuation.evaluate(event); }\n                catch (Exception ex) { System.out.println("[actuate exception] RTV: " + ex); runner.halt(); return; }\n                for (Actuator a : actuators) {'),
        ('                        a.actuate(bp, event);','                        V011Actuation.actuate(a, bp, concrete);'),
        ('                        System.out.println("      [actuate exception] " + ex);','                        System.out.println("      [actuate exception] " + ex);\n                        runner.halt(); return;'),
        ('        runner.run();','        V011Actuation.begin(program);\n        try { runner.run(); } finally { V011Actuation.end(actuators); }')]
    for old,new in edits:
        if source.count(old)!=1:raise RuntimeError('Runtime patch anchor changed: '+old)
        source=source.replace(old,new)
    boundary='    private static RunResult runScenario('
    if source.split(boundary)[0]!=original.split(boundary)[0]:raise RuntimeError('Scenario catalog changed')
    return source+'\n'
