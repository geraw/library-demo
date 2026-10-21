import json, re, sys

ACTIVE = {"open", "in-progress", "awaiting-approval"}
events = []
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    match = re.search(r"MODEL_EVENT\s+(\{.*\})", line)
    if match:
        try: events.append(json.loads(match.group(1)))
        except json.JSONDecodeError: pass

orders = {}
three_active = False
two_garages = False
for event in events:
    if event.get("kind") != "api_success": continue
    method, path, response = event.get("method"), event.get("path", ""), event.get("response")
    if method == "POST" and path == "/repair-orders" and isinstance(response, dict):
        if all(response.get(key) for key in ("roId", "carVin", "customerId", "garageId", "status")):
            orders[response["roId"]] = response
    elif method == "PUT" and path.startswith("/repair-orders/") and isinstance(response, dict):
        orders[response.get("roId", path.rsplit("/", 1)[-1])] = response
    elif method == "DELETE" and path.startswith("/repair-orders/"):
        orders.pop(path.rsplit("/", 1)[-1], None)
    elif method == "POST" and (path.endswith("/approve") or path.endswith("/close")) and isinstance(response, dict):
        if response.get("roId"): orders[response["roId"]] = response

    active = [item for item in orders.values() if item.get("status") in ACTIVE]
    by_garage, by_car = {}, {}
    for item in active:
        by_garage.setdefault(item["garageId"], set()).add(item["roId"])
        by_car.setdefault(item["carVin"], set()).add(item["garageId"])
    three_active |= any(len(value) >= 3 for value in by_garage.values())
    two_garages |= any(len(value) >= 2 for value in by_car.values())

print(json.dumps({
    "rule_basis": "HTTP/SUT event trace; evaluator is external to generated stories",
    "three_active_orders_confirmed": three_active,
    "one_car_two_garages_confirmed": two_garages,
    "event_count": len(events)
}, indent=2))
