import il.ac.bgu.cs.bp.bpjs.execution.BProgramRunner;
import il.ac.bgu.cs.bp.bpjs.execution.listeners.BProgramRunnerListenerAdapter;
import il.ac.bgu.cs.bp.bpjs.internal.Pair;
import il.ac.bgu.cs.bp.bpjs.model.BEvent;
import il.ac.bgu.cs.bp.bpjs.model.BProgram;
import il.ac.bgu.cs.bp.bpjs.model.BProgramSyncSnapshot;
import il.ac.bgu.cs.bp.bpjs.model.SyncStatement;
import il.ac.bgu.cs.bp.bpjs.model.eventselection.AbstractEventSelectionStrategy;
import il.ac.bgu.cs.bp.bpjs.model.eventsets.EventSet;
import il.ac.bgu.cs.bp.bpjs.model.eventsets.EventSets;
import testory.bprogram.Actuator;
import testory.bprogram.TestoryBProgram;
import testory.bprogram.TestoryBProgramBuilder;
import testory.configs.RunOptions;
import testory.libraries.rest.RESTActuator;
import testory.libraries.rest.RESTLibrary;
import testory.reports.ActuationSummary;
import testory.reports.LoggerArtifact;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Paths;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import static java.util.stream.Collectors.toList;
import static java.util.stream.Collectors.toSet;

/**
 * Sibling of SimpleGuidedRun.java, same trick (fixed step order, single global counter, no
 * identity tracking) but aimed at a different question: not "does createLoan ever get reached"
 * but "once createBook and createUser have each been selected once, what is the *entire* set of
 * createLoan chooser events the model offers?" -- valid and invalid variants alike.
 *
 * Drives createBook -> createUser deterministically exactly like SimpleGuidedRun. Once both are
 * done, every synchronization point is inspected for currently-offered ("requested and not
 * blocked") events whose chooser name starts with "createLoan"; each newly-seen one is printed in
 * full the first time it appears. The run keeps going (letting other, unrelated bthreads
 * interleave) so that createLoan variants which only become enabled later still get discovered,
 * but a *valid* createLoan is still nudged towards selection so the run concludes instead of
 * spinning forever.
 *
 * Requires the SUT running (python sut.py, localhost:23242) and Provengo.uber.jar on the
 * classpath.
 *
 * Run:
 *   javac -cp Provengo.uber.jar -d out src/ShowCreateLoanOptions.java
 *   java -cp "Provengo.uber.jar:out" ShowCreateLoanOptions <path-to-provengo-project>
 *
 * Set env var GUIDEDRUN_TRACE=1 to log every selected event, chooser and concrete alike.
 */
public class ShowCreateLoanOptions {

    /** createBook -> createUser, in that order. No identity constraint between them. */
    private static final String[] SETUP_ACTIONS = {"createBook", "createUser"};

    /** Hard cap on events processed after setup, regardless of discovery progress. */
    private static final int MAX_EVENTS_AFTER_SETUP = 20000;

    /** Once this many consecutive post-setup events go by without a *new* createLoan option
     *  category being discovered, we consider the catalog complete and stop -- otherwise the run
     *  never ends, since background bthreads keep minting fresh book/user ids forever. Raised well
     *  past the 400 used earlier: we're now specifically testing for the *absence* of a genuine,
     *  non-sentinel valid createLoan sighting, so a longer, more confident run is worth the time. */
    private static final int STABLE_EVENTS_TO_STOP = 3000;

    private static final boolean DEBUG_TRACE = System.getenv("GUIDEDRUN_TRACE") != null;

    private static final String SUT_RESET_URL = "http://localhost:23242/reset";

    /** Matches a deliberately-nonexistent id (generateMissingId(): existingId + 1_000_000_000). */
    private static final java.util.regex.Pattern NONEXISTENT_ID = java.util.regex.Pattern.compile("\\d{9,}");

    /** Chooser names end in ": <id>" or ": <id>/<id>" (the concrete book/user ids used for that
     *  particular request). Stripping that suffix collapses e.g. "createLoan (valid-standard):
     *  7/3" and "createLoan (valid-standard): 12/9" into the same category, since otherwise the
     *  catalog would grow forever as background bthreads keep creating new books and users. */
    private static final java.util.regex.Pattern ID_SUFFIX = java.util.regex.Pattern.compile("^(.*):\\s*\\d+(?:/\\d+)?$");

    private static String category(String chooserName) {
        if (chooserName == null) return null;
        java.util.regex.Matcher m = ID_SUFFIX.matcher(chooserName);
        return m.matches() ? m.group(1) : chooserName;
    }

    /** Recursively renders BPjs script objects (which implement Map/List but don't override
     *  toString, printing as "[object Object]") into readable JSON-ish text. */
    private static String prettyPrint(Object value) {
        StringBuilder sb = new StringBuilder();
        prettyPrint(value, sb);
        return sb.toString();
    }

    @SuppressWarnings("unchecked")
    private static void prettyPrint(Object value, StringBuilder sb) {
        if (value instanceof Map) {
            Map<String, Object> map = (Map<String, Object>) value;
            sb.append("{");
            boolean first = true;
            for (Map.Entry<String, Object> entry : map.entrySet()) {
                if (!first) sb.append(", ");
                first = false;
                sb.append(entry.getKey()).append(": ");
                prettyPrint(entry.getValue(), sb);
            }
            sb.append("}");
        } else if (value instanceof List) {
            List<Object> list = (List<Object>) value;
            sb.append("[");
            boolean first = true;
            for (Object item : list) {
                if (!first) sb.append(", ");
                first = false;
                prettyPrint(item, sb);
            }
            sb.append("]");
        } else if (value instanceof String) {
            sb.append("\"").append(value).append("\"");
        } else {
            sb.append(value);
        }
    }

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
     *  the HTTP verb ("POST"), carrying its descriptive name at data.model.name instead. */
    private static String chooserName(BEvent event) {
        Map<String, Object> data = eventData(event);
        Map<String, Object> model = data == null ? null : asMap(data.get("model"));
        if (model != null && model.get("name") != null) {
            return String.valueOf(model.get("name"));
        }
        return event.getName();
    }

    /** "<METHOD> <path>" for a concrete REST event, for logging only. */
    private static String requestLine(BEvent event) {
        Map<String, Object> data = eventData(event);
        if (data == null) return event.getName();
        Object methodRaw = data.get("method");
        String method = methodRaw == null ? event.getName() : String.valueOf(methodRaw);
        Object raw = data.get("path");
        if (raw == null) raw = data.get("url");
        if (raw == null) return method;
        String path = String.valueOf(raw).replaceFirst("^https?://[^/]+", "");
        int q = path.indexOf('?');
        path = q >= 0 ? path.substring(0, q) : path;
        return method + " " + path;
    }

    /**
     * Event selection strategy that (a) deterministically drives createBook -> createUser to
     * completion, exactly like SimpleGuidedRun's prioritizer, then (b) once both exist, records
     * the full set of currently-offered events whose chooser name starts with "createLoan" at
     * every synchronization point -- not just the one that ends up selected -- while still
     * favoring a valid createLoan so the run eventually concludes.
     */
    private static class DiscoveringEss extends AbstractEventSelectionStrategy {

        final AtomicInteger setupStep = new AtomicInteger(0);
        final AtomicInteger eventsSinceSetupDone = new AtomicInteger(0);
        final AtomicInteger eventsSinceNewCategory = new AtomicInteger(0);
        final AtomicInteger selectableEventsCalls = new AtomicInteger(0);
        /** Distinct createLoan option *categories* (id-suffix stripped) -> one example chooser
         *  name for that category, in discovery order. */
        final Map<String, String> categories = new java.util.LinkedHashMap<>();
        /** Every distinct chooser name that ever satisfied chooserNameMatches(name, "createLoan")
         *  -- i.e. was genuinely offered as priority-1000-eligible: real ids, not the missing-id
         *  sentinel, not an "invalid" variant. Tracked separately from `categories` (which dedupes
         *  by stripping ids) specifically to answer: does a *real*, non-sentinel valid createLoan
         *  ever even get offered at all, regardless of whether it's ever actually selected? */
        final Map<String, String> genuineSightings = new java.util.LinkedHashMap<>();
        volatile boolean setupDone = false;
        /** Snapshot of every createLoan-prefixed candidate (name -> priority) seen in the most
         *  recent selectableEvents() call, for the eventSelected listener to dump the instant a
         *  createLoan variant actually gets picked -- so we can see every sibling that was (or
         *  wasn't) sitting alongside it in that exact round. */
        volatile List<String> lastRoundCreateLoanCandidates = Collections.emptyList();
        /** Real (non-sentinel) id-suffixes ("userId/bookId") already diagnosed by the
         *  invalid-siblings-but-no-valid-siblings probe below, so we only dump the deep detail
         *  once per suffix instead of flooding output every round it persists. */
        final Set<String> diagnosedSuffixes = new java.util.HashSet<>();
        private static final java.util.regex.Pattern REAL_SUFFIX = java.util.regex.Pattern.compile(": (\\d+)/(\\d+)$");

        @Override
        public Set<BEvent> selectableEvents(BProgramSyncSnapshot bpss) {
            selectableEventsCalls.incrementAndGet();
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

            List<String> roundCreateLoanCandidates = new java.util.ArrayList<>();
            for (BEvent e : possibleOptions) {
                String n = chooserName(e);
                if (n != null && n.startsWith("createLoan")) {
                    roundCreateLoanCandidates.add(n + "  [prio=" + prioritize(e) + "]");
                }
            }
            lastRoundCreateLoanCandidates = roundCreateLoanCandidates;

            if (setupDone) {
                diagnoseRealPairsMissingValidSiblings(statements, blocked, possibleOptions);
            }

            if (setupDone) {
                boolean foundNew = false;
                for (BEvent e : possibleOptions) {
                    String name = chooserName(e);
                    if (name == null || !name.startsWith("createLoan")) continue;
                    String cat = category(name);
                    if (categories.putIfAbsent(cat, name) == null) {
                        foundNew = true;
                        System.out.println();
                        System.out.println("  >>> discovered createLoan option #" + categories.size() + ": " + cat);
                        System.out.println("      example chooser : " + name);
                        System.out.println("      full event name : " + e.getName());
                        System.out.println("      request         : " + requestLine(e));
                        System.out.println("      data            : " + prettyPrint(eventData(e)));
                    }
                    // Separately: does this exact instance genuinely qualify for priority 1000
                    // (real ids, valid, not the missing-id sentinel)? This is NOT deduped by
                    // category -- it's the direct, un-stripped chooserNameMatches check that
                    // prioritize() itself uses, logged every time it is newly seen at all.
                    if (chooserNameMatches(name, "createLoan") && genuineSightings.putIfAbsent(name, name) == null) {
                        System.out.println();
                        System.out.println("  *** GENUINE VALID createLoan OFFERED (round " + selectableEventsCalls.get()
                                + ", " + genuineSightings.size() + " so far): " + name);
                        System.out.println("      data : " + prettyPrint(eventData(e)));
                    }
                }
                eventsSinceNewCategory.set(foundNew ? 0 : eventsSinceNewCategory.get() + 1);
            }

            List<Pair<BEvent, Integer>> prioritized = possibleOptions.stream()
                    .map(e -> new Pair<>(e, prioritize(e)))
                    .sorted((p1, p2) -> p2.getRight() - p1.getRight())
                    .collect(toList());

            int max = prioritized.get(0).getRight();
            return prioritized.stream().takeWhile(p -> p.getRight() == max).map(Pair::getLeft)
                    .collect(toSet());
        }

        /**
         * For every real (non-sentinel) "userId/bookId" suffix that has at least one
         * createLoan-invalid candidate but zero createLoan-valid* candidates in this round's
         * possibleOptions, dumps, once per suffix: (a) whether the missing valid siblings are
         * present in the RAW (pre-block) request set of the statement that offered the invalid
         * one -- i.e. were they filtered out by some *other* bthread's block(), or were they
         * never even requested at all -- and (b), if filtered, which statement's block EventSet
         * is catching them.
         */
        private void diagnoseRealPairsMissingValidSiblings(Set<SyncStatement> statements, EventSet blocked, Set<BEvent> possibleOptions) {
            Map<String, Boolean> suffixHasValid = new java.util.HashMap<>();
            Map<String, BEvent> suffixInvalidExample = new java.util.HashMap<>();
            for (BEvent e : possibleOptions) {
                String name = chooserName(e);
                if (name == null || !name.startsWith("createLoan")) continue;
                java.util.regex.Matcher m = REAL_SUFFIX.matcher(name);
                if (!m.find()) continue;
                String suffix = m.group(1) + "/" + m.group(2);
                if (NONEXISTENT_ID.matcher(suffix).find()) continue; // skip sentinel pairs
                boolean isValidShaped = name.contains("valid") && !name.contains("invalid");
                suffixHasValid.merge(suffix, isValidShaped, (a, b) -> a || b);
                if (!isValidShaped) suffixInvalidExample.putIfAbsent(suffix, e);
            }

            for (Map.Entry<String, Boolean> entry : suffixHasValid.entrySet()) {
                String suffix = entry.getKey();
                if (entry.getValue()) continue; // has a valid sibling -- nothing to diagnose
                if (!diagnosedSuffixes.add(suffix)) continue; // already diagnosed this suffix

                System.out.println();
                System.out.println("  !!! DIAGNOSTIC: pair " + suffix + " has invalid createLoan candidates "
                        + "but NO valid-shaped sibling in possibleOptions this round.");
                BEvent invalidExample = suffixInvalidExample.get(suffix);

                // Which statement produced this invalid candidate? Check its RAW (unfiltered)
                // request set for the valid-shaped siblings that should share the same array.
                for (SyncStatement s : statements) {
                    Set<BEvent> raw = getRequestedAndNotBlocked(s, EventSets.none);
                    if (!raw.contains(invalidExample)) continue;
                    System.out.println("      statement raw (pre-block) request set size: " + raw.size());
                    List<BEvent> rawValids = raw.stream()
                            .filter(ev -> { String n = chooserName(ev); return n != null && n.contains(suffix) && n.contains("valid") && !n.contains("invalid"); })
                            .collect(toList());
                    if (rawValids.isEmpty()) {
                        System.out.println("      -> valid siblings for " + suffix + " are ABSENT even before block-filtering: "
                                + "this statement's own request set never included them.");
                        System.out.println("      -> full raw request set for this statement:");
                        for (BEvent ev : raw) {
                            System.out.println("           - " + chooserName(ev));
                        }
                    } else {
                        System.out.println("      -> valid siblings ARE in the raw request set but were filtered out by 'blocked'. Checking which statement's block() is catching them:");
                        for (BEvent validEv : rawValids) {
                            System.out.println("         valid candidate: " + chooserName(validEv));
                            for (SyncStatement s2 : statements) {
                                EventSet b = s2.getBlock();
                                if (b != null && b != EventSets.none && b.contains(validEv)) {
                                    System.out.println("           BLOCKED by statement whose block() = " + b);
                                }
                            }
                        }
                    }
                    break;
                }
            }
        }

        private int prioritize(BEvent e) {
            if (!setupDone) {
                int i = setupStep.get();
                if (i < SETUP_ACTIONS.length && chooserNameMatches(chooserName(e), SETUP_ACTIONS[i])) return 1000;
                return 0;
            }
            // Setup already done: nudge towards a *valid* createLoan so the run can conclude,
            // without that priority we'd wander through unrelated bthreads forever.
            return chooserNameMatches(chooserName(e), "createLoan") ? 1000 : 0;
        }

        void noteSelected(BEvent event) {
            if (setupDone) return;
            int i = setupStep.get();
            if (i < SETUP_ACTIONS.length && chooserNameMatches(chooserName(event), SETUP_ACTIONS[i])) {
                int reached = setupStep.incrementAndGet();
                System.out.println("  >>> setup step " + reached + "/" + SETUP_ACTIONS.length
                        + " (" + SETUP_ACTIONS[i] + ") reached via: " + chooserName(event));
                if (reached >= SETUP_ACTIONS.length) {
                    setupDone = true;
                    System.out.println("  >>> book and user created -- now recording every createLoan option offered");
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            System.err.println("Usage: java ShowCreateLoanOptions <path-to-library/provengo-project>");
            System.exit(1);
        }
        String projectPath = args[0];
        resetSut();

        RunOptions runOptions = new RunOptions(new String[]{"run", projectPath});
        TestoryBProgramBuilder builder = new TestoryBProgramBuilder(runOptions);
        builder.setProjectDirectory(Paths.get(projectPath));
        TestoryBProgram program = builder.build();

        DiscoveringEss ess = new DiscoveringEss();
        program.setEventSelectionStrategy(ess);

        // Our own minimal BProgramRunner setup (unlike the real `provengo run` CLI) never wires
        // up an actuator, so selected REST events were never actually being sent anywhere -- every
        // earlier run in this investigation was effectively equivalent to `provengo run --dry`.
        // Wire the real REST actuator in by hand so selected events actually hit the SUT.
        Actuator restActuator = new RESTActuator(runOptions);
        restActuator.setup(runOptions);

        BProgramRunner runner = new BProgramRunner(program);
        final AtomicInteger createLoanSelectionsDumped = new AtomicInteger(0);
        runner.addListener(new BProgramRunnerListenerAdapter() {
            @Override
            public void eventSelected(BProgram bp, BEvent event) {
                if (DEBUG_TRACE) {
                    System.out.println("      [trace] " + chooserName(event) + " " + requestLine(event));
                }
                if (RESTLibrary.isRestEvent(event)) {
                    try {
                        restActuator.actuate(bp, event).ifPresent(summary -> {
                            for (LoggerArtifact artifact : summary.getArtifacts()) {
                                System.out.println("      [actuated] " + artifact.getArtifactsTitle() + ":");
                                System.out.println("        " + new String(artifact.getContent(), StandardCharsets.UTF_8).replace("\n", "\n        "));
                            }
                        });
                    } catch (Exception ex) {
                        System.out.println("      [actuation FAILED] " + chooserName(event) + " -- " + ex);
                    }
                }
                ess.noteSelected(event);
                if (ess.setupDone) {
                    String selectedName = chooserName(event);
                    if (selectedName != null && selectedName.startsWith("createLoan")
                            && createLoanSelectionsDumped.incrementAndGet() <= 25) {
                        System.out.println();
                        System.out.println("  === createLoan SELECTED: " + selectedName
                                + "  (siblings offered in that same round:)");
                        for (String cand : ess.lastRoundCreateLoanCandidates) {
                            System.out.println("        - " + cand);
                        }
                    }
                    int c = ess.eventsSinceSetupDone.incrementAndGet();
                    int stable = ess.eventsSinceNewCategory.get();
                    if (chooserNameMatches(chooserName(event), "createLoan")) {
                        System.out.println();
                        System.out.println("  >>> valid createLoan selected: " + chooserName(event) + " -- halting.");
                        System.out.println();
                        System.out.println("  >>> actual SUT state right after actuation:");
                        System.out.println("      GET /loans -> " + httpGet("/loans"));
                        System.out.println("      GET /books -> " + httpGet("/books"));
                        System.out.println("      GET /users -> " + httpGet("/users"));
                        runner.halt();
                    } else if (stable >= STABLE_EVENTS_TO_STOP) {
                        System.out.println("  >>> no new createLoan option in the last " + stable
                                + " events -- catalog looks complete, halting.");
                        runner.halt();
                    } else if (c >= MAX_EVENTS_AFTER_SETUP) {
                        System.out.println("  >>> giving up after " + c + " events post-setup (hard cap reached).");
                        runner.halt();
                    }
                }
            }
        });

        runner.run();

        System.out.println();
        System.out.println("=========== createLoan option categories discovered (post book+user) ===========");
        if (ess.categories.isEmpty()) {
            System.out.println("(none -- createLoan was never offered after book+user were created)");
        } else {
            int i = 1;
            for (Map.Entry<String, String> entry : ess.categories.entrySet()) {
                System.out.println("  " + (i++) + ". " + entry.getKey() + "   [e.g. " + entry.getValue() + "]");
            }
        }

        System.out.println();
        System.out.println("=========== genuine (real-id, non-sentinel) valid createLoan sightings ===========");
        System.out.println("  selectableEvents() rounds observed: " + ess.selectableEventsCalls.get());
        if (ess.genuineSightings.isEmpty()) {
            System.out.println("  NONE -- a real valid createLoan chooser event was never once offered as a candidate.");
        } else {
            int i = 1;
            for (String name : ess.genuineSightings.keySet()) {
                System.out.println("  " + (i++) + ". " + name);
            }
        }
    }

    private static String httpGet(String path) {
        try {
            URL url = new URL("http://localhost:23242" + path);
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("GET");
            int code = conn.getResponseCode();
            java.io.InputStream in = code < 400 ? conn.getInputStream() : conn.getErrorStream();
            String body = new String(in.readAllBytes(), StandardCharsets.UTF_8);
            conn.disconnect();
            return "HTTP " + code + " " + body;
        } catch (Exception e) {
            return "(failed: " + e.getMessage() + ")";
        }
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
                System.out.println("  (note: SUT has no /reset endpoint (HTTP " + code + ") -- state accumulates, harmless here since ids never repeat)");
            }
            conn.disconnect();
        } catch (Exception e) {
            System.out.println("  (warning: could not reach SUT before this run: " + e.getMessage()
                    + " -- is `python sut.py` running on localhost:23242?)");
        }
    }
}
