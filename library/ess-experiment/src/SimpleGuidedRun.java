import il.ac.bgu.cs.bp.bpjs.execution.BProgramRunner;
import il.ac.bgu.cs.bp.bpjs.execution.listeners.BProgramRunnerListenerAdapter;
import il.ac.bgu.cs.bp.bpjs.model.BEvent;
import il.ac.bgu.cs.bp.bpjs.model.BProgram;
import testory.bprogram.PrioritizedEventsESS;
import testory.bprogram.TestoryBProgram;
import testory.bprogram.TestoryBProgramBuilder;
import testory.configs.RunOptions;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Paths;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Deliberately dumb counterpart to GuidedRun.java: no identity tracking, no bindings, no
 * requires/binds bookkeeping -- just a fixed, ordered array of action names and a single global
 * counter for how far along it we are. The event selection strategy scores an event 1000 if its
 * chooser name matches ACTIONS[counter], 0 otherwise; on a match the counter advances.
 *
 * Exists to strip away every other moving part while isolating one question: once createBook
 * and createUser have each been selected once, does createLoan's own valid chooser event ever
 * become selectable at all? If it doesn't, the cause is not in this file's matching logic (there
 * isn't any left to be wrong) -- it's upstream, in how createLoan is offered.
 *
 * Requires the SUT running (python sut.py, localhost:23242) and Provengo.uber.jar on the
 * classpath.
 *
 * Run:
 *   javac -cp Provengo.uber.jar -d out src/SimpleGuidedRun.java
 *   java -cp "Provengo.uber.jar:out" SimpleGuidedRun <path-to-provengo-project>
 *
 * Set env var GUIDEDRUN_TRACE=1 to log every selected event, chooser and concrete alike.
 */
public class SimpleGuidedRun {

    /** addBook -> addUser -> addLoan, in that order. No identity constraint between them. */
    private static final String[] ACTIONS = {"createBook", "createUser", "createLoan"};

    /** How many selected events may go by with no step progress before an attempt is
     *  abandoned as inconclusive. */
    private static final int MAX_EVENTS_WITHOUT_PROGRESS = 3000;
    private static final int ATTEMPTS = 10;
    private static final boolean DEBUG_TRACE = System.getenv("GUIDEDRUN_TRACE") != null;

    private static final String SUT_RESET_URL = "http://localhost:23242/reset";

    /** Matches a deliberately-nonexistent id (generateMissingId(): existingId + 1_000_000_000). */
    private static final java.util.regex.Pattern NONEXISTENT_ID = java.util.regex.Pattern.compile("\\d{9,}");

    private static boolean chooserNameMatches(String eventName, String action) {
        if (eventName == null) return false;
        return eventName.startsWith(action)
                && eventName.contains("valid")
                && !eventName.contains("invalid")
                && !NONEXISTENT_ID.matcher(eventName).find();
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : null;
    }

    private static Map<String, Object> eventData(BEvent event) {
        return asMap(event == null ? null : event.getData());
    }

    /** A single-sync action (e.g. createLoan) offers the concrete REST event itself, named after
     *  the HTTP verb ("POST"), carrying its descriptive name at data.variant.name instead. */
    private static String chooserName(BEvent event) {
        Map<String, Object> data = eventData(event);
        if (data != null) {
            Map<String, Object> variant = asMap(data.get("variant"));
            if (variant != null && variant.get("name") != null) {
                return String.valueOf(variant.get("name"));
            }
        }
        return event.getName();
    }

    /** Normalized request path from a concrete REST event, for trace logging only. */
    private static String requestPath(BEvent event) {
        Map<String, Object> data = eventData(event);
        if (data == null) return "";
        Object raw = data.get("path");
        if (raw == null) raw = data.get("url");
        if (raw == null) return "";
        String path = String.valueOf(raw).replaceFirst("^https?://[^/]+", "");
        int q = path.indexOf('?');
        return q >= 0 ? path.substring(0, q) : path;
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            System.err.println("Usage: java SimpleGuidedRun <path-to-library/provengo-project>");
            System.exit(1);
        }
        String projectPath = args[0];

        boolean reached = false;
        int attemptsUsed = 0;
        for (int attempt = 1; attempt <= ATTEMPTS; attempt++) {
            attemptsUsed = attempt;
            System.out.println();
            System.out.println("--- attempt " + attempt + "/" + ATTEMPTS + " ---");
            resetSut();
            reached = runOnce(projectPath);
            if (reached) break; // one witness is enough
        }

        System.out.println();
        System.out.println("=========== RESULT ===========");
        System.out.println((reached
                ? "REACHED (witness found on attempt " + attemptsUsed + "/" + ATTEMPTS + ")"
                : "NOT FOUND after " + ATTEMPTS + " attempts (inconclusive)")
                + "  " + String.join(" -> ", ACTIONS));
    }

    private static void resetSut() {
        try {
            URL url = new URL(SUT_RESET_URL);
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setDoOutput(true);
            try (OutputStream os = conn.getOutputStream()) {
                os.write("{}".getBytes(StandardCharsets.UTF_8));
            }
            int code = conn.getResponseCode();
            if (code != 200) {
                System.out.println("  (note: SUT has no /reset endpoint (HTTP " + code + ") -- state accumulates across attempts, harmless here since ids never repeat)");
            }
            conn.disconnect();
        } catch (Exception e) {
            System.out.println("  (warning: could not reach SUT before this attempt: " + e.getMessage()
                    + " -- is `python sut.py` running on localhost:23242?)");
        }
    }

    private static boolean runOnce(String projectPath) throws Exception {
        System.out.println("### " + String.join(" -> ", ACTIONS));

        RunOptions runOptions = new RunOptions(new String[]{"run", projectPath});
        TestoryBProgramBuilder builder = new TestoryBProgramBuilder(runOptions);
        builder.setProjectDirectory(Paths.get(projectPath));
        TestoryBProgram program = builder.build();

        // The one piece of state this whole class keeps: how far along ACTIONS we are.
        final AtomicInteger counter = new AtomicInteger(0);
        final AtomicInteger eventsSinceProgress = new AtomicInteger(0);

        PrioritizedEventsESS ess = new PrioritizedEventsESS();
        ess.setPrioritizer(event -> {
            int i = counter.get();
            if (i >= ACTIONS.length) return 0;
            return chooserNameMatches(chooserName(event), ACTIONS[i]) ? 1000 : 0;
        });
        program.setEventSelectionStrategy(ess);

        BProgramRunner runner = new BProgramRunner(program);
        runner.addListener(new BProgramRunnerListenerAdapter() {
            @Override
            public void eventSelected(BProgram bp, BEvent event) {
                if (DEBUG_TRACE) {
                    System.out.println("      [trace] " + chooserName(event) + " path=" + requestPath(event));
                }
                int i = counter.get();
                if (i >= ACTIONS.length) return;

                if (chooserNameMatches(chooserName(event), ACTIONS[i])) {
                    int reached = counter.incrementAndGet();
                    eventsSinceProgress.set(0);
                    System.out.println("  >>> step " + reached + "/" + ACTIONS.length
                            + " (" + ACTIONS[i] + ") reached via: " + chooserName(event));
                    if (reached >= ACTIONS.length) {
                        System.out.println("  >>> full sequence reached, halting.");
                        runner.halt();
                    }
                    return;
                }

                int c = eventsSinceProgress.incrementAndGet();
                if (c >= MAX_EVENTS_WITHOUT_PROGRESS) {
                    System.out.println("  >>> giving up: " + c + " events with no progress past step " + i
                            + " (" + ACTIONS[i] + ")");
                    runner.halt();
                }
            }
        });

        runner.run();

        int reachedSteps = counter.get();
        boolean reached = reachedSteps >= ACTIONS.length;
        System.out.println("### Result: " + (reached ? "REACHED" : "NOT FOUND")
                + " (completed steps " + reachedSteps + "/" + ACTIONS.length + ")");
        return reached;
    }
}
