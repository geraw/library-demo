import il.ac.bgu.cs.bp.bpjs.model.BEvent;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Names a single-event REST action the way StrictGuidedRun's catalog matching expects.
 *
 * The single-event model (library/provengo on branch single-event-actions) offers each action as
 * one concrete REST event named after its HTTP verb ("POST", "DELETE", "GET") with no data.model
 * block. The catalog matches an action by a descriptive name: it must start with the action
 * ("createLoan"), contain "valid", not contain "invalid", and not contain a nonexistent 10-digit
 * id. This class derives such a name from the event's transport shape alone:
 *
 *   method + path            -> createBook / deleteLoan / readBookDetail / readLoans ...
 *   expectedResponseCodes    -> "(valid)" for 2xx, "(invalid - expects [400])" otherwise
 *   parameters id/userId/bookId -> the identity suffix (a missing id of 1000000001+ stays visible)
 *
 * No request is inspected for anything the catalog did not already depend on.
 */
public final class V013Match {

    private static final Map<String, String> ENTITY = Map.of(
            "books", "Book", "users", "User", "loans", "Loan", "holds", "Hold");

    private V013Match() {}

    public static String actionName(BEvent event) {
        Object raw = event.getData();
        if (!(raw instanceof Map)) return event.getName();
        Map<?, ?> data = (Map<?, ?>) raw;
        if (!"REST".equals(data.get("lib"))) return event.getName();

        String method = String.valueOf(data.get("method")).toUpperCase();
        String path = String.valueOf(data.get("url")).replaceFirst("^https?://[^/]+", "");
        int query = path.indexOf('?');
        if (query >= 0) path = path.substring(0, query);
        List<String> segments = new ArrayList<>();
        for (String s : path.split("/")) if (!s.isEmpty()) segments.add(s);
        if (segments.isEmpty() || !ENTITY.containsKey(segments.get(0))) return event.getName();
        String entity = ENTITY.get(segments.get(0));

        String action;
        switch (method) {
            case "POST": action = "create" + entity; break;
            case "DELETE": action = "delete" + entity; break;
            case "GET": action = segments.size() == 2 && entity.equals("Book") ? "readBookDetail" : "read" + entity + "s"; break;
            default: action = method.toLowerCase() + entity;
        }

        List<Integer> codes = new ArrayList<>();
        Object expected = data.get("expectedResponseCodes");
        if (expected instanceof List) {
            for (Object o : (List<?>) expected) if (o instanceof Number) codes.add(((Number) o).intValue());
        }
        boolean success = !codes.isEmpty();
        for (int code : codes) if (code < 200 || code >= 300) success = false;

        Map<?, ?> parameters = data.get("parameters") instanceof Map ? (Map<?, ?>) data.get("parameters") : Map.of();
        return action + (success ? " (valid): " : " (invalid - expects " + codes + "): ") + identity(parameters);
    }

    private static String identity(Map<?, ?> parameters) {
        Object id = parameters.get("id"), userId = parameters.get("userId"), bookId = parameters.get("bookId");
        StringBuilder label = new StringBuilder();
        if (id != null) label.append(number(id));
        if (userId != null || bookId != null) {
            if (label.length() > 0) label.append(' ');
            label.append(number(userId)).append('/').append(number(bookId));
        }
        if (label.length() == 0 && parameters.get("description") != null) label.append(parameters.get("description"));
        return label.toString();
    }

    private static String number(Object value) {
        if (value instanceof Number) {
            double d = ((Number) value).doubleValue();
            if (d == Math.rint(d)) return String.valueOf((long) d);
        }
        return String.valueOf(value);
    }
}
