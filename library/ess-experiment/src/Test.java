import il.ac.bgu.cs.bp.bpjs.execution.BProgramRunner;
import il.ac.bgu.cs.bp.bpjs.execution.listeners.BProgramRunnerListenerAdapter;
import il.ac.bgu.cs.bp.bpjs.model.BEvent;
import il.ac.bgu.cs.bp.bpjs.model.BProgram;
import il.ac.bgu.cs.bp.bpjs.model.BProgramSyncSnapshot;
import il.ac.bgu.cs.bp.bpjs.model.eventselection.EventSelectionResult;
import il.ac.bgu.cs.bp.bpjs.model.eventselection.EventSelectionStrategy;
import il.ac.bgu.cs.bp.bpjs.model.eventselection.SimpleEventSelectionStrategy;
import testory.bprogram.Actuator;
import testory.bprogram.TestoryBProgram;
import testory.bprogram.TestoryBProgramBuilder;
import testory.configs.RunOptions;
import testory.libraries.TestoryLibrary;

import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Random;
import java.util.Set;

/**
 * Create one user, one book. Then watch whether createHold ever gets offered for exactly that
 * pair.
 *
 * Run:
 *   javac -cp Provengo.uber.jar -d out src/Test.java
 *   java -cp "Provengo.uber.jar;out" Test <path-to-provengo-project>
 */
public class Test {

    @SuppressWarnings("unchecked")
    private static Map<String, Object> params(BEvent e) {
        Map<String, Object> data = (Map<String, Object>) e.getData();
        Map<String, Object> p = (Map<String, Object>) data.get("parameters");
        if (p != null) return p;
        Map<String, Object> variant = (Map<String, Object>) data.get("variant");
        return variant == null ? null : (Map<String, Object>) variant.get("parameters");
    }

    @SuppressWarnings("unchecked")
    private static String name(BEvent e) {
        Map<String, Object> variant = (Map<String, Object>) ((Map<String, Object>) e.getData()).get("variant");
        return variant != null && variant.get("name") != null ? String.valueOf(variant.get("name")) : e.getName();
    }

    private static Double num(Object o) {
        return o instanceof Number ? ((Number) o).doubleValue() : null;
    }

    /** True for a well-formed, success-intended chooser of exactly this action (not "invalid - ..."). */
    private static boolean isValid(BEvent e, String action) {
        String n = name(e);
        return n.startsWith(action + " (") && n.contains("valid") && !n.contains("invalid");
    }

    private static BEvent findValid(Set<BEvent> offered, String action) {
        for (BEvent e : offered) if (isValid(e, action)) return e;
        return null;
    }

    public static void main(String[] args) throws Exception {
        String projectPath = args[0];
        RunOptions opts = new RunOptions(new String[]{"run", projectPath});
        TestoryBProgramBuilder builder = new TestoryBProgramBuilder(opts);
        builder.setProjectDirectory(Paths.get(projectPath));
        TestoryBProgram program = builder.build();

        List<Actuator> actuators = new ArrayList<>();
        for (TestoryLibrary lib : builder.getLibrariesInUse()) {
            lib.getActuator(opts).ifPresent(a -> { a.setup(opts); actuators.add(a); });
        }

        final Double[] userId = {null};
        final Double[] bookId = {null};
        final int[] round = {0};
        final Random rng = new Random();

        program.setEventSelectionStrategy(new EventSelectionStrategy() {
            final SimpleEventSelectionStrategy base = new SimpleEventSelectionStrategy();

            public Set<BEvent> selectableEvents(BProgramSyncSnapshot s) { return base.selectableEvents(s); }

            public Optional<EventSelectionResult> select(BProgramSyncSnapshot s, Set<BEvent> offered) {
                BEvent pick;
                if (userId[0] == null) {
                    pick = findValid(offered, "createUser");
                } else if (bookId[0] == null) {
                    pick = findValid(offered, "createBook");
                } else {
                    pick = watchForHold(offered);
                }
                if (pick != null) return Optional.of(new EventSelectionResult(pick));
                if (round[0] >= 100) return Optional.empty();
                return Optional.of(new EventSelectionResult(pickToAdvanceContext(offered)));
            }

            /** Same plain uniform-random pick BPjs's own default strategy uses -- no filtering. */
            private BEvent pickToAdvanceContext(Set<BEvent> offered) {
                List<BEvent> pool = new ArrayList<>(offered);
                return pool.get(rng.nextInt(pool.size()));
            }

            /** Returns the exact createHold(userId, bookId) event if on offer, else null. */
            private BEvent watchForHold(Set<BEvent> offered) {
                round[0]++;
                if (round[0] == 1 || round[0] == 100) dumpAll(offered);
                int holdCount = 0;
                for (BEvent e : offered) {
                    if (!name(e).startsWith("createHold")) continue;
                    holdCount++;
                    Map<String, Object> p = params(e);
                    if (p != null && userId[0].equals(num(p.get("userId"))) && bookId[0].equals(num(p.get("bookId")))) {
                        System.out.println(">>> FOUND: " + name(e));
                        return e;
                    }
                }
                if (round[0] == 100) {
                    System.out.println(">>> NOT FOUND after 100 rounds. createHold offers this round: " + holdCount
                            + " / " + offered.size() + " total -- none for userId=" + userId[0] + " bookId=" + bookId[0]);
                }
                return null;
            }

            private void dumpAll(Set<BEvent> offered) {
                System.out.println(">>> DUMP: all " + offered.size() + " events offered right now:");
                List<String> lines = new ArrayList<>();
                for (BEvent e : offered) {
                    Map<String, Object> p = params(e);
                    String info = p == null ? "" : "  id=" + num(p.get("id")) + " userId=" + num(p.get("userId")) + " bookId=" + num(p.get("bookId"));
                    lines.add("    " + name(e) + info);
                }
                java.util.Collections.sort(lines);
                lines.forEach(System.out::println);
                System.out.println(">>> end of dump");
            }
        });

        BProgramRunner runner = new BProgramRunner(program);
        runner.addListener(new BProgramRunnerListenerAdapter() {
            public void eventSelected(BProgram bp, BEvent e) {
                for (Actuator a : actuators) { try { a.actuate(bp, e); } catch (Exception ignored) {} }
                if (userId[0] == null && isValid(e, "createUser")) {
                    userId[0] = num(params(e).get("id"));
                    System.out.println("created user " + userId[0]);
                } else if (bookId[0] == null && isValid(e, "createBook")) {
                    bookId[0] = num(params(e).get("id"));
                    System.out.println("created book " + bookId[0] + " -- now watching for createHold(" + userId[0] + "," + bookId[0] + ")");
                }
            }
        });

        runner.run();
    }
}
