import il.ac.bgu.cs.bp.bpjs.execution.BProgramRunner;
import il.ac.bgu.cs.bp.bpjs.execution.listeners.BProgramRunnerListenerAdapter;
import il.ac.bgu.cs.bp.bpjs.model.BEvent;
import il.ac.bgu.cs.bp.bpjs.model.BProgram;
import il.ac.bgu.cs.bp.bpjs.model.BProgramSyncSnapshot;
import il.ac.bgu.cs.bp.bpjs.model.SyncStatement;
import il.ac.bgu.cs.bp.bpjs.model.eventselection.AbstractEventSelectionStrategy;
import il.ac.bgu.cs.bp.bpjs.model.eventsets.EventSet;
import il.ac.bgu.cs.bp.bpjs.model.eventsets.EventSets;
import testory.bprogram.TestoryBProgram;
import testory.bprogram.TestoryBProgramBuilder;
import testory.configs.RunOptions;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static java.util.stream.Collectors.toSet;

/**
 * Checks whether a hand-written sequence of events ("script") is a legal run of the model, by
 * literally walking it: at every synchronization point, look for a currently-selectable event
 * that matches the script's next step. If one exists, select *only* that event (forcing it) and
 * advance to the next step. If none exists, the script cannot proceed *right now* - stop
 * immediately and declare that step unreachable. No priorities, no scoring, no waiting around
 * for other b-threads to maybe make it available later: a legal next step must already be a
 * candidate the moment we look for it.
 *
 * A script that runs to completion describes a run we confirmed the model allows. A script that
 * stops before its last step describes a run the model does not allow to complete - which is
 * exactly what we want for a script built to describe a scenario we expect to be *illegal*.
 *
 * Run:
 *   javac -cp Provengo.uber.jar -d out src/ScenarioCheck.java
 *   java -cp "Provengo.uber.jar:out" ScenarioCheck <path-to-provengo-project>
 */
public class ScenarioCheck {

    private static final String SUT_RESET_URL = "http://localhost:23242/reset";
    private static final Pattern NONEXISTENT_ID = Pattern.compile("\\d{9,}");
    private static final Pattern SUFFIX = Pattern.compile(": (\\d+)/(\\d+)$");

    // ------------------------------------------------------------------
    // Chooser-event helpers (same conventions as ShowCreateLoanOptions.java)
    // ------------------------------------------------------------------

    private static boolean isValidChooser(String eventName, String action) {
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

    private static String chooserName(BEvent event) {
        Map<String, Object> data = eventData(event);
        Map<String, Object> model = data == null ? null : asMap(data.get("model"));
        if (model != null && model.get("name") != null) return String.valueOf(model.get("name"));
        return event.getName();
    }

    /** Parses the "userId/bookId" suffix off a chooser name, e.g. "...: 5/3" -> {"5","3"}. */
    private static String[] suffixOf(String name) {
        Matcher m = SUFFIX.matcher(name);
        return m.find() ? new String[]{m.group(1), m.group(2)} : null;
    }

    // ------------------------------------------------------------------
    // The script itself: an ordered list of steps, each just a "is this the one" predicate.
    // ------------------------------------------------------------------

    interface Step {
        boolean matches(BEvent candidate);
        String describe();
    }

    /** The common case: the next valid chooser event whose name starts with `action`. */
    private static Step action(String action) {
        return new Step() {
            public boolean matches(BEvent e) { return isValidChooser(chooserName(e), action); }
            public String describe() { return action + " (any)"; }
        };
    }

    /** Wraps `inner`; whenever a candidate satisfies it, also records that candidate's
     *  "userId/bookId" suffix into `into` - e.g. so a later step can refer to "this same user". */
    private static Step recordingSuffix(Step inner, String[] into) {
        return new Step() {
            public boolean matches(BEvent e) {
                if (!inner.matches(e)) return false;
                String[] suffix = suffixOf(chooserName(e));
                if (suffix != null) { into[0] = suffix[0]; into[1] = suffix[1]; }
                return true;
            }
            public String describe() { return inner.describe(); }
        };
    }

    // ------------------------------------------------------------------
    // The ESS: walks `script` by direct inspection, no scoring.
    // ------------------------------------------------------------------

    private static class ScriptEss extends AbstractEventSelectionStrategy {
        final List<Step> script;
        final AtomicInteger stepIndex = new AtomicInteger(0);

        ScriptEss(List<Step> script) { this.script = script; }

        @Override
        public Set<BEvent> selectableEvents(BProgramSyncSnapshot bpss) {
            Set<SyncStatement> statements = bpss.getStatements();
            EventSet blocked = EventSets.anyOf(statements.stream()
                    .filter(Objects::nonNull)
                    .map(SyncStatement::getBlock)
                    .filter(r -> r != EventSets.none)
                    .collect(toSet()));
            Set<BEvent> possibleOptions = statements.stream()
                    .flatMap(s -> getRequestedAndNotBlocked(s, blocked).stream())
                    .collect(toSet());
            if (possibleOptions.isEmpty()) return Collections.emptySet();

            int i = stepIndex.get();
            if (i >= script.size()) return possibleOptions; // script finished; nothing left to force

            Step next = script.get(i);
            for (BEvent candidate : possibleOptions) {
                if (next.matches(candidate)) {
                    return Collections.singleton(candidate); // the next step IS a candidate right now: force it, nothing else
                }
            }
            // The next step is not a candidate right now: the script cannot proceed. Offering
            // nothing brings the b-program to a stop instead of letting anything else happen.
            return Collections.emptySet();
        }
    }

    // ------------------------------------------------------------------
    // Running one scenario and reporting PASS/FAIL.
    // ------------------------------------------------------------------

    static class Scenario {
        final String name;
        final List<Step> script;
        /** true if the script describes a run we expect the model to allow to completion; false
         *  if it describes a run we expect the model to make impossible to finish. */
        final boolean expectCompletion;
        Scenario(String name, boolean expectCompletion, Step... steps) {
            this.name = name;
            this.expectCompletion = expectCompletion;
            this.script = new ArrayList<>(List.of(steps));
        }
    }

    static class Result {
        final String name;
        final boolean passed;
        final String detail;
        Result(String name, boolean passed, String detail) {
            this.name = name;
            this.passed = passed;
            this.detail = detail;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            System.err.println("Usage: java ScenarioCheck <path-to-library/provengo-project>");
            System.exit(1);
        }
        String projectPath = args[0];

        // Scenarios we want to exist: the script should run to completion.
        Scenario p1 = new Scenario("P1: createBook -> createUser -> createLoan completes", true,
                action("createBook"), action("createUser"), action("createLoan"));
        Scenario p2 = new Scenario("P2: createBook -> createUser -> createHold completes", true,
                action("createBook"), action("createUser"), action("createHold"));

        // Scenarios we do NOT want to exist: the script should get stuck before its last step.
        // Both "forbidden" scenarios below need to refer to "this exact same user" in a later
        // step, so the first loan's step records its userId/bookId suffix as it's reached.
        String[] busyUser1 = new String[2];
        Step secondLoanSameUserOtherBook = new Step() {
            public boolean matches(BEvent e) {
                String name = chooserName(e);
                if (!isValidChooser(name, "createLoan")) return false;
                String[] suffix = suffixOf(name);
                return suffix != null && suffix[0].equals(busyUser1[0]) && !suffix[1].equals(busyUser1[1]);
            }
            public String describe() { return "createLoan for user " + busyUser1[0] + " on a book other than " + busyUser1[1]; }
        };
        Scenario n1 = new Scenario("N1: a second createLoan for an already-busy user must NOT complete", false,
                action("createBook"), action("createBook"), action("createUser"),
                recordingSuffix(action("createLoan"), busyUser1), secondLoanSameUserOtherBook);

        String[] busyUser2 = new String[2];
        Step deleteThatSameUser = new Step() {
            public boolean matches(BEvent e) {
                String name = chooserName(e);
                return name != null && name.startsWith("deleteUser (valid)") && name.endsWith(": " + busyUser2[0]);
            }
            public String describe() { return "deleteUser for user " + busyUser2[0]; }
        };
        Scenario n2 = new Scenario("N2: deleteUser for a user with an active loan must NOT complete", false,
                action("createBook"), action("createUser"), recordingSuffix(action("createLoan"), busyUser2), deleteThatSameUser);

        List<Result> results = new ArrayList<>();
        for (Scenario s : List.of(p1, p2, n1, n2)) {
            results.add(run(s, projectPath));
        }

        System.out.println();
        System.out.println("=========== SCENARIO SUMMARY ===========");
        boolean allPassed = true;
        for (Result r : results) {
            System.out.println((r.passed ? "  PASS  " : "  FAIL  ") + r.name);
            System.out.println("          " + r.detail);
            allPassed &= r.passed;
        }
        System.out.println();
        System.out.println(allPassed ? "ALL SCENARIOS PASSED" : "SOME SCENARIOS FAILED");
    }

    private static Result run(Scenario scenario, String projectPath) throws Exception {
        System.out.println();
        System.out.println("### " + scenario.name);
        resetSut();

        RunOptions runOptions = new RunOptions(new String[]{"run", projectPath});
        TestoryBProgramBuilder builder = new TestoryBProgramBuilder(runOptions);
        builder.setProjectDirectory(Paths.get(projectPath));
        TestoryBProgram program = builder.build();

        ScriptEss ess = new ScriptEss(scenario.script);
        program.setEventSelectionStrategy(ess);

        BProgramRunner runner = new BProgramRunner(program);
        boolean[] completed = {false};

        runner.addListener(new BProgramRunnerListenerAdapter() {
            @Override
            public void eventSelected(BProgram bp, BEvent event) {
                int i = ess.stepIndex.get();
                if (i >= scenario.script.size() || !scenario.script.get(i).matches(event)) return;
                System.out.println("  >>> step " + (i + 1) + "/" + scenario.script.size()
                        + " (" + scenario.script.get(i).describe() + ") reached via: " + chooserName(event));
                if (ess.stepIndex.incrementAndGet() >= scenario.script.size()) {
                    completed[0] = true;
                    runner.halt();
                }
            }
        });
        runner.run();

        int reachedStep = ess.stepIndex.get();
        boolean passed = scenario.expectCompletion == completed[0];
        String detail = completed[0]
                ? "script completed all " + scenario.script.size() + " steps"
                : "stopped at step " + (reachedStep + 1) + "/" + scenario.script.size()
                        + " (" + scenario.script.get(reachedStep).describe() + ") - not currently a candidate";
        return new Result(scenario.name, passed, detail);
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
            conn.getResponseCode();
            conn.disconnect();
        } catch (Exception e) {
            System.out.println("  (warning: could not reach SUT before this scenario: " + e.getMessage() + ")");
        }
    }
}
