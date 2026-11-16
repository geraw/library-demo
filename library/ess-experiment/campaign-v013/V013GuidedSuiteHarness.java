import java.io.IOException;
import java.io.PrintStream;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/**
 * Adapter around the frozen StrictGuidedRun (v013-patched copy): runs the catalog and/or the v013
 * additions one scenario per fresh runtime, with a verified case boundary before each one.
 *
 *   V013GuidedSuiteHarness <model> <native.jsonl> <caseTimeoutSeconds> [options]
 *     --set catalog,v013-common,v013-contract | all     which scenario lists (default all)
 *     --only <substring>                                 keep scenarios whose name contains it
 *     --boundary observer | direct                       case reset through the observer's
 *                                                        /__campaign__/case (default) or the
 *                                                        SUT's own /reset
 *     --reset-url <url>                                  override the boundary URL
 *     --list                                             print the selection and exit
 *     --smoke                                            run only the transport self-check
 */
public class V013GuidedSuiteHarness {

    static String quote(Object value) {
        if (value == null) return "null";
        String s = value.toString();
        StringBuilder b = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            if (c == '"' || c == '\\') b.append('\\').append(c);
            else if (c < 32) b.append(String.format("\\u%04x", (int) c));
            else b.append(c);
        }
        return b.append('"').toString();
    }

    static volatile int actuatorErrors, listenerErrors;

    static class Monitor extends PrintStream {
        Monitor(PrintStream out) { super(out, true); }
        @Override public void println(String s) {
            if (s != null && s.contains("[actuate exception]")) actuatorErrors++;
            if (s != null && s.contains("[ERROR]")) listenerErrors++;
            super.println(s);
        }
    }

    static class Selected {
        final String set;
        final StrictGuidedRun.Scenario scenario;
        Selected(String set, StrictGuidedRun.Scenario scenario) { this.set = set; this.scenario = scenario; }
    }

    @SuppressWarnings("unchecked")
    static List<StrictGuidedRun.Scenario> catalog() throws Exception {
        Field field = StrictGuidedRun.class.getDeclaredField("SCENARIOS");
        field.setAccessible(true);
        return (List<StrictGuidedRun.Scenario>) field.get(null);
    }

    public static void main(String[] args) throws Exception {
        String model = args[0], output = args[1];
        int caseTimeout = Integer.parseInt(args[2]);
        List<String> sets = List.of("catalog", "v013-common", "v013-contract");
        String only = null, boundary = "observer", resetUrl = null;
        boolean list = false, smoke = false;
        for (int i = 3; i < args.length; i++) {
            switch (args[i]) {
                case "--set": sets = args[++i].equals("all") ? sets : Arrays.asList(args[i].split(",")); break;
                case "--only": only = args[++i]; break;
                case "--boundary": boundary = args[++i]; break;
                case "--reset-url": resetUrl = args[++i]; break;
                case "--list": list = true; break;
                case "--smoke": smoke = true; break;
                default: throw new IllegalArgumentException("Unknown option " + args[i]);
            }
        }
        if (resetUrl == null) {
            resetUrl = boundary.equals("direct") ? "http://localhost:23242/reset" : "http://127.0.0.1:23243/__campaign__/case";
        }

        List<Selected> selected = new ArrayList<>();
        if (smoke) {
            selected.add(new Selected("smoke", V013Scenarios.smoke()));
        } else {
            for (String set : sets) {
                List<StrictGuidedRun.Scenario> source;
                switch (set) {
                    case "catalog": source = catalog(); break;
                    case "v013-common": source = V013Scenarios.COMMON; break;
                    case "v013-contract": source = V013Scenarios.CONTRACT; break;
                    default: throw new IllegalArgumentException("Unknown scenario set " + set);
                }
                for (StrictGuidedRun.Scenario s : source) {
                    if (only == null || s.name.contains(only)) selected.add(new Selected(set, s));
                }
            }
        }
        if (list) {
            System.out.println("SCENARIO_COUNT=" + selected.size());
            for (Selected s : selected) System.out.println(s.set + "\t" + s.scenario.steps.size() + "\t" + s.scenario.expectReached + "\t" + s.scenario.name);
            return;
        }

        System.setOut(new Monitor(System.out));
        System.setErr(new Monitor(System.err));
        HttpClient client = HttpClient.newBuilder().connectTimeout(java.time.Duration.ofSeconds(10)).build();
        Method run = StrictGuidedRun.class.getDeclaredMethod("runScenario", String.class, StrictGuidedRun.Scenario.class);
        run.setAccessible(true);

        try (PrintWriter results = new PrintWriter(Files.newBufferedWriter(Path.of(output)))) {
            int index = 0;
            for (Selected item : selected) {
                index++;
                final int caseIndex = index;
                StrictGuidedRun.Scenario scenario = item.scenario;
                String body = boundary.equals("direct") ? "{}" : "{\"case\":" + index + "}";
                HttpResponse<String> reset = client.send(HttpRequest.newBuilder(URI.create(resetUrl))
                        .timeout(java.time.Duration.ofSeconds(20)).header("Content-Type", "application/json")
                        .POST(HttpRequest.BodyPublishers.ofString(body)).build(), HttpResponse.BodyHandlers.ofString());
                if (reset.statusCode() != 200) throw new IOException("Case reset failed: " + reset.body());

                actuatorErrors = 0; listenerErrors = 0;
                long start = System.nanoTime();
                FutureTask<Object> task = new FutureTask<>(() -> run.invoke(null, model, scenario));
                Thread thread = new Thread(task, "scenario-" + caseIndex);
                thread.setDaemon(true);
                thread.start();
                Object result = null; String error = null; boolean timeout = false;
                try { result = task.get(caseTimeout, TimeUnit.SECONDS); }
                catch (TimeoutException e) { error = "CASE_TIMEOUT"; timeout = true; }
                catch (Exception e) { error = e.toString(); if (e.getCause() != null) error += "; " + e.getCause(); }

                boolean reached = false; int reachedSteps = 0; Object failedAction = null;
                if (result != null) {
                    Field f = result.getClass().getDeclaredField("reached"); f.setAccessible(true); reached = (boolean) f.get(result);
                    f = result.getClass().getDeclaredField("reachedSteps"); f.setAccessible(true); reachedSteps = (int) f.get(result);
                    f = result.getClass().getDeclaredField("failedAction"); f.setAccessible(true); failedAction = f.get(result);
                }
                boolean pass = result != null && reached == scenario.expectReached && actuatorErrors == 0 && listenerErrors == 0;
                results.println("{\"case\":" + index + ",\"set\":" + quote(item.set) + ",\"name\":" + quote(scenario.name)
                        + ",\"steps\":" + scenario.steps.size() + ",\"expectReached\":" + scenario.expectReached
                        + ",\"reached\":" + reached + ",\"reachedSteps\":" + reachedSteps
                        + ",\"failedAction\":" + quote(failedAction)
                        + ",\"actuator_errors\":" + actuatorErrors + ",\"listener_errors\":" + listenerErrors
                        + ",\"exception\":" + quote(error) + ",\"native_pass\":" + pass
                        + ",\"wall_seconds\":" + ((System.nanoTime() - start) / 1e9) + "}");
                results.flush();
                System.out.println("V013_CASE " + index + "/" + selected.size() + " PASS=" + pass);
                if (timeout) System.exit(124); // Never reset while an unfinished scenario can still issue requests.
            }
        }
        System.exit(0);
    }
}
