import il.ac.bgu.cs.bp.bpjs.BPjs;
import il.ac.bgu.cs.bp.bpjs.model.BProgram;
import il.ac.bgu.cs.bp.bpjs.model.BEvent;
import org.mozilla.javascript.Context;
import testory.bprogram.Actuator;
import testory.libraries.runtimevalues.RuntimeValuesManager;
import testory.reports.ActuationSummary;
import java.util.List;
import java.util.Optional;

/** Restore the native event evaluation and actuation-result checks omitted by StrictGuidedRun. */
public final class V011Actuation {
    private static final ThreadLocal<Context> contexts = new ThreadLocal<>();
    public static void begin(BProgram program) {
        Context context=BPjs.enterRhinoContext(); contexts.set(context);
        RuntimeValuesManager.setCurrent(new RuntimeValuesManager(context,program));
    }
    public static BEvent evaluate(BEvent event) {
        return RuntimeValuesManager.getCurrent().evaluate(event);
    }
    public static void actuate(Actuator actuator,BProgram program,BEvent event) throws Exception {
        Optional<ActuationSummary> summary=actuator.actuate(program,event);
        if(summary.isPresent()&&summary.get().notOk())
            throw new IllegalStateException("Native actuation failed: "+summary.get().getResult()+"; "+summary.get().getRemarks());
    }
    public static void end(List<Actuator> actuators) {
        try {for(Actuator a:actuators)a.clean();}
        finally {
            RuntimeValuesManager.setCurrent(null);
            Context context=contexts.get();contexts.remove();if(context!=null)context.close();
        }
    }
}
