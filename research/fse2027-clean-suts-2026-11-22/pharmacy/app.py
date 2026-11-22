import json
import re

from flask import Flask, jsonify, request
from flask_cors import CORS


_OPENAPI_DOCUMENT = json.loads('{"openapi":"3.0.3","info":{"title":"Pharmacy REST SUT","version":"2.0.0","description":"Clean stateful Pharmacy benchmark API. Request bodies are checked against these schemas at runtime."},"servers":[{"url":"http://127.0.0.1:5000"}],"paths":{"/drugs":{"x-key":"id","get":{"summary":"List drugs","responses":{"200":{"description":"list","content":{"application/json":{"schema":{"type":"array","items":{"$ref":"#/components/schemas/Drug"}}}}},"400":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}}},"post":{"summary":"Create drug","requestBody":{"required":true,"content":{"application/json":{"schema":{"$ref":"#/components/schemas/Drug"}}}},"responses":{"201":{"description":"created","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Drug"}}}},"400":{"description":"missing required key (id) or malformed request","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"duplicate drug (conflict)","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"x-create-expected-codes":[201,200],"x-duplicate-policy":"conflict","x-duplicate-expected-codes":[409,400]}},"/drugs/{id}":{"parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"string"}}],"get":{"summary":"Get drug","responses":{"200":{"description":"ok","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Drug"}}}},"400":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"string"}}]},"put":{"summary":"Update drug","requestBody":{"required":true,"content":{"application/json":{"schema":{"$ref":"#/components/schemas/DrugUpdate"}}}},"responses":{"200":{"description":"updated","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Drug"}}}},"400":{"description":"Request body failed OpenAPI type validation","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"string"}}]},"delete":{"summary":"Delete drug (idempotent)","responses":{"200":{"description":"deleted or did not exist","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Deleted"}}}},"400":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"x-delete-idempotent":true,"x-negative-delete-expected-codes":[200,404,401],"parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"string"}}]}},"/patients":{"x-key":"id","get":{"summary":"List patients","responses":{"200":{"description":"list","content":{"application/json":{"schema":{"type":"array","items":{"$ref":"#/components/schemas/Patient"}}}}},"400":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}}},"post":{"summary":"Create patient","requestBody":{"required":true,"content":{"application/json":{"schema":{"$ref":"#/components/schemas/Patient"}}}},"responses":{"201":{"description":"created","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Patient"}}}},"400":{"description":"missing required key (id) or malformed request","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"duplicate patient (conflict)","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"x-create-expected-codes":[201,200],"x-duplicate-policy":"conflict","x-duplicate-expected-codes":[409,400]}},"/patients/{id}":{"parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"string"}}],"get":{"summary":"Get patient","responses":{"200":{"description":"ok","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Patient"}}}},"400":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"string"}}]},"put":{"summary":"Update patient","requestBody":{"required":true,"content":{"application/json":{"schema":{"$ref":"#/components/schemas/PatientUpdate"}}}},"responses":{"200":{"description":"updated","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Patient"}}}},"400":{"description":"Request body failed OpenAPI type validation","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"string"}}]},"delete":{"summary":"Delete patient (idempotent)","responses":{"200":{"description":"deleted or did not exist","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Deleted"}}}},"400":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"x-delete-idempotent":true,"x-negative-delete-expected-codes":[200,404,401],"parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"string"}}]}},"/orders":{"x-key":"id","get":{"summary":"List orders","responses":{"200":{"description":"list","content":{"application/json":{"schema":{"type":"array","items":{"$ref":"#/components/schemas/Order"}}}}},"400":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}}},"post":{"summary":"Create order","requestBody":{"required":true,"content":{"application/json":{"schema":{"$ref":"#/components/schemas/Order"}}}},"responses":{"201":{"description":"created","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Order"}}}},"400":{"description":"missing required key (id) or malformed request","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"duplicate order (conflict)","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"x-create-expected-codes":[201,200],"x-duplicate-policy":"conflict","x-duplicate-expected-codes":[409,400]}},"/orders/{id}":{"parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"string"}}],"get":{"summary":"Get order","responses":{"200":{"description":"ok","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Order"}}}},"400":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"string"}}]},"put":{"summary":"Update order","requestBody":{"required":true,"content":{"application/json":{"schema":{"$ref":"#/components/schemas/OrderUpdate"}}}},"responses":{"200":{"description":"updated","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Order"}}}},"400":{"description":"Request body failed OpenAPI type validation","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"string"}}]},"delete":{"summary":"Delete order (idempotent)","responses":{"200":{"description":"deleted or did not exist","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Deleted"}}}},"400":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"x-delete-idempotent":true,"x-negative-delete-expected-codes":[200,404,401],"parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"string"}}]}},"/prescriptions":{"x-key":"id","get":{"summary":"List prescriptions","responses":{"200":{"description":"list","content":{"application/json":{"schema":{"type":"array","items":{"$ref":"#/components/schemas/Prescription"}}}}},"400":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}}},"post":{"summary":"Create prescription","requestBody":{"required":true,"content":{"application/json":{"schema":{"$ref":"#/components/schemas/PrescriptionCreate"}}}},"responses":{"201":{"description":"created","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Prescription"}}}},"400":{"description":"missing required key (id) or malformed request","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"duplicate prescription (conflict)","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"x-create-expected-codes":[201,200],"x-duplicate-policy":"conflict","x-duplicate-expected-codes":[409,400]}},"/prescriptions/{id}":{"parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"string"}}],"get":{"summary":"Get prescription","responses":{"200":{"description":"ok","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Prescription"}}}},"400":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"string"}}]},"put":{"summary":"Update prescription","requestBody":{"required":true,"content":{"application/json":{"schema":{"$ref":"#/components/schemas/PrescriptionUpdate"}}}},"responses":{"200":{"description":"updated","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Prescription"}}}},"400":{"description":"Request body failed OpenAPI type validation","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"string"}}]},"delete":{"summary":"Delete prescription (idempotent)","responses":{"200":{"description":"deleted or did not exist","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Deleted"}}}},"400":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"x-delete-idempotent":true,"x-negative-delete-expected-codes":[200,404,401],"parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"string"}}]}},"/inventory":{"x-key":"ndc","get":{"summary":"List inventory","responses":{"200":{"description":"list","content":{"application/json":{"schema":{"type":"array","items":{"$ref":"#/components/schemas/Inventory"}}}}},"400":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}}},"post":{"summary":"Create inventor","requestBody":{"required":true,"content":{"application/json":{"schema":{"$ref":"#/components/schemas/Inventory"}}}},"responses":{"201":{"description":"created","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Inventory"}}}},"400":{"description":"missing required key (ndc) or malformed request","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"duplicate inventory (conflict)","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"x-create-expected-codes":[201,200],"x-duplicate-policy":"conflict","x-duplicate-expected-codes":[409,400]}},"/inventory/{ndc}":{"parameters":[{"name":"ndc","in":"path","required":true,"schema":{"type":"string"}}],"get":{"summary":"Get inventor","responses":{"200":{"description":"ok","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Inventory"}}}},"400":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"parameters":[{"name":"ndc","in":"path","required":true,"schema":{"type":"string"}}]},"put":{"summary":"Update inventor","requestBody":{"required":true,"content":{"application/json":{"schema":{"$ref":"#/components/schemas/InventoryUpdate"}}}},"responses":{"200":{"description":"updated","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Inventory"}}}},"400":{"description":"Request body failed OpenAPI type validation","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"parameters":[{"name":"ndc","in":"path","required":true,"schema":{"type":"string"}}]},"delete":{"summary":"Delete inventor (idempotent)","responses":{"200":{"description":"deleted or did not exist","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Deleted"}}}},"400":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}},"x-delete-idempotent":true,"x-negative-delete-expected-codes":[200,404,401],"parameters":[{"name":"ndc","in":"path","required":true,"schema":{"type":"string"}}]}},"/stores":{"post":{"summary":"Create or update a pharmacy store","requestBody":{"required":true,"content":{"application/json":{"schema":{"$ref":"#/components/schemas/Store"}}}},"responses":{"201":{"description":"store recorded","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Store"}}}},"400":{"description":"missing required field","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}}}},"/stores/{id}":{"get":{"summary":"Get a pharmacy store","parameters":[{"name":"id","in":"path","required":true,"schema":{"type":"string"}}],"responses":{"200":{"description":"store","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Store"}}}},"404":{"description":"store not found","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"400":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}}}},"/dispense":{"post":{"summary":"Dispense a prescription refill","requestBody":{"required":true,"content":{"application/json":{"schema":{"$ref":"#/components/schemas/DispenseRequest"}}}},"responses":{"201":{"description":"dispense operation completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/DispenseResult"}}}},"404":{"description":"prescription not found","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"prescription cannot be dispensed in its current state","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"500":{"description":"server error","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"400":{"description":"Request body failed OpenAPI type validation","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}}}},"/process-rx":{"post":{"summary":"Process a prescription at a pharmacy store","requestBody":{"required":true,"content":{"application/json":{"schema":{"$ref":"#/components/schemas/ProcessPrescriptionRequest"}}}},"responses":{"201":{"description":"prescription processed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/ProcessPrescriptionResult"}}}},"404":{"description":"prescription not found","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"prescription cannot be processed by the requested store","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"500":{"description":"server error","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"400":{"description":"Request body failed OpenAPI type validation","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}}}},"/reset":{"post":{"operationId":"resetPharmacy","summary":"Clear all Pharmacy state","responses":{"200":{"description":"State reset","content":{"application/json":{"schema":{"$ref":"#/components/schemas/ResetResult"}}}},"400":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"404":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"409":{"description":"Request could not be completed","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}}}}}},"components":{"schemas":{"Error":{"type":"object","properties":{"error":{"type":"string"}},"required":["error"],"additionalProperties":true},"Deleted":{"type":"object","properties":{"deleted":{"type":"string"}},"required":["deleted"],"additionalProperties":false},"ResetResult":{"type":"object","properties":{"status":{"type":"string","enum":["reset"]}},"required":["status"],"additionalProperties":false},"Drug":{"type":"object","properties":{"id":{"type":"string"},"name":{"type":"string"}},"required":["id"],"additionalProperties":true},"DrugUpdate":{"type":"object","properties":{"id":{"type":"string"},"name":{"type":"string"}},"additionalProperties":true},"Patient":{"type":"object","properties":{"id":{"type":"string"},"name":{"type":"string"}},"required":["id"],"additionalProperties":true},"PatientUpdate":{"type":"object","properties":{"id":{"type":"string"},"name":{"type":"string"}},"additionalProperties":true},"Order":{"type":"object","properties":{"id":{"type":"string"}},"required":["id"],"additionalProperties":true},"OrderUpdate":{"type":"object","properties":{"id":{"type":"string"}},"additionalProperties":true},"Prescription":{"type":"object","properties":{"id":{"type":"string"},"refillsLeft":{"type":"integer","minimum":0},"lockedByStoreId":{"type":"string","nullable":true}},"required":["id"],"additionalProperties":true},"PrescriptionUpdate":{"type":"object","properties":{"id":{"type":"string"},"refillsLeft":{"type":"integer","minimum":0}},"additionalProperties":true},"Inventory":{"type":"object","properties":{"ndc":{"type":"string"}},"required":["ndc"],"additionalProperties":true},"InventoryUpdate":{"type":"object","properties":{"ndc":{"type":"string"}},"additionalProperties":true},"Store":{"type":"object","properties":{"storeId":{"type":"string"},"phone":{"type":"string"}},"required":["storeId","phone"],"additionalProperties":true},"DispenseRequest":{"type":"object","properties":{"rxId":{"type":"string"},"status":{"type":"string"}},"required":["rxId"],"additionalProperties":true},"DispenseResult":{"type":"object","properties":{"status":{"type":"string","enum":["dispensed"]},"remaining":{"type":"integer","minimum":0}},"required":["status","remaining"],"additionalProperties":false},"ProcessPrescriptionRequest":{"type":"object","properties":{"rxId":{"type":"string"},"storeId":{"type":"string"},"status":{"type":"string"},"complaint":{"type":"string"}},"required":["rxId","storeId"],"additionalProperties":true},"ProcessPrescriptionResult":{"type":"object","properties":{"status":{"type":"string","enum":["processed"]},"store":{"type":"string"}},"required":["status","store"],"additionalProperties":false},"PrescriptionCreate":{"type":"object","properties":{"id":{"type":"string"},"refillsLeft":{"type":"integer","minimum":0}},"required":["id"],"additionalProperties":true}}}}')


def _resolve_ref(ref, document):
    if not ref.startswith("#/components/schemas/"):
        raise ValueError(f"Unsupported schema reference: {ref}")
    name = ref.rsplit("/", 1)[-1]
    return document.get("components", {}).get("schemas", {}).get(name)


def _matches_type(value, expected):
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _validate(value, schema, document, location="$", depth=0):
    if depth > 40:
        return [f"{location}: schema nesting limit exceeded"]
    if "$ref" in schema:
        resolved = _resolve_ref(schema["$ref"], document)
        if resolved is None:
            return [f"{location}: unresolved schema reference {schema['$ref']}"]
        return _validate(value, resolved, document, location, depth + 1)

    errors = []
    if value is None and schema.get("nullable"):
        return errors
    expected = schema.get("type")
    if expected and not _matches_type(value, expected):
        return [f"{location}: expected {expected}, received {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{location}: value is outside the allowed enum")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{location}.{key}: required property is missing")
        for key, item in value.items():
            if key in properties:
                errors.extend(_validate(item, properties[key], document, f"{location}.{key}", depth + 1))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{location}.{key}: additional property is not allowed")
            elif isinstance(schema.get("additionalProperties"), dict):
                errors.extend(_validate(item, schema["additionalProperties"], document, f"{location}.{key}", depth + 1))
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            errors.extend(_validate(item, schema["items"], document, f"{location}[{index}]", depth + 1))
    for key, predicate, label in (
        ("minimum", lambda n, limit: n >= limit, "minimum"),
        ("maximum", lambda n, limit: n <= limit, "maximum"),
        ("minLength", lambda n, limit: n >= limit, "minLength"),
        ("maxLength", lambda n, limit: n <= limit, "maxLength"),
        ("minItems", lambda n, limit: n >= limit, "minItems"),
        ("maxItems", lambda n, limit: n <= limit, "maxItems"),
    ):
        if key in schema:
            measured = len(value) if key in ("minLength", "maxLength", "minItems", "maxItems") else value
            if isinstance(measured, (int, float)) and not isinstance(measured, bool) and not predicate(measured, schema[key]):
                errors.append(f"{location}: violates {label}={schema[key]}")
    if "pattern" in schema and isinstance(value, str) and re.search(schema["pattern"], value) is None:
        errors.append(f"{location}: value does not match the required pattern")
    return errors


def attach_openapi_validator(app, document):
    @app.before_request
    def validate_openapi_request():
        if request.url_rule is None:
            return None
        route = re.sub(r"<(?:(?:[^:>]+):)?([^>]+)>", r"{\1}", request.url_rule.rule)
        operation = document.get("paths", {}).get(route, {}).get(request.method.lower())
        if not operation or "requestBody" not in operation:
            return None
        content = operation["requestBody"].get("content", {})
        body_schema = content.get("application/json", {}).get("schema")
        if body_schema is None:
            return None
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 400
        payload = request.get_json(silent=True)
        if payload is None:
            return jsonify({"error": "Request body must contain valid JSON"}), 400
        errors = _validate(payload, body_schema, document)
        if errors:
            return jsonify({"error": "Request body does not match OpenAPI schema", "details": errors}), 400
        return None




def create_app():
    app = Flask(__name__)
    CORS(app)
    attach_openapi_validator(app, _OPENAPI_DOCUMENT)

    stores = {
        "drugs": {},
        "patients": {},
        "orders": {},
        "prescriptions": {},
        "inventory": {},
        "pharmacy_stores": {},
    }

    def list_items(collection):
        return jsonify(list(stores[collection].values())), 200

    def create_item(collection, key_name, label, defaults=None):
        payload = dict(request.get_json(silent=True))
        key = payload[key_name]
        if key in stores[collection]:
            return jsonify({"error": f"{label} {key} already exists"}), 409
        item = dict(defaults or {})
        if collection == "prescriptions":
            payload.pop("lockedByStoreId", None)
        item.update(payload)
        if collection == "prescriptions":
            item["lockedByStoreId"] = None
        stores[collection][key] = item
        return jsonify(item), 201

    def read_item(collection, key):
        item = stores[collection].get(key)
        if item is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(item), 200

    def update_item(collection, key_name, key):
        payload = dict(request.get_json(silent=True))
        if collection == "prescriptions":
            payload.pop("lockedByStoreId", None)
        item = dict(stores[collection].get(key, {key_name: key}))
        item.update(payload)
        item[key_name] = key
        stores[collection][key] = item
        return jsonify(item), 200

    def delete_item(collection, key):
        stores[collection].pop(key, None)
        return jsonify({"deleted": key}), 200

    @app.post("/reset")
    def reset():
        for collection in stores.values():
            collection.clear()
        return jsonify({"status": "reset"}), 200

    @app.get("/drugs")
    def list_drugs():
        return list_items("drugs")

    @app.post("/drugs")
    def add_drug():
        return create_item("drugs", "id", "drug")

    @app.get("/drugs/<id>")
    def get_drug(id):
        return read_item("drugs", id)

    @app.put("/drugs/<id>")
    def put_drug(id):
        return update_item("drugs", "id", id)

    @app.delete("/drugs/<id>")
    def delete_drug(id):
        return delete_item("drugs", id)

    @app.get("/patients")
    def list_patients():
        return list_items("patients")

    @app.post("/patients")
    def add_patient():
        return create_item("patients", "id", "patient")

    @app.get("/patients/<id>")
    def get_patient(id):
        return read_item("patients", id)

    @app.put("/patients/<id>")
    def put_patient(id):
        return update_item("patients", "id", id)

    @app.delete("/patients/<id>")
    def delete_patient(id):
        return delete_item("patients", id)

    @app.get("/orders")
    def list_orders():
        return list_items("orders")

    @app.post("/orders")
    def add_order():
        return create_item("orders", "id", "order")

    @app.get("/orders/<id>")
    def get_order(id):
        return read_item("orders", id)

    @app.put("/orders/<id>")
    def put_order(id):
        return update_item("orders", "id", id)

    @app.delete("/orders/<id>")
    def delete_order(id):
        return delete_item("orders", id)

    @app.get("/prescriptions")
    def list_prescriptions():
        return list_items("prescriptions")

    @app.post("/prescriptions")
    def add_prescription():
        return create_item(
            "prescriptions",
            "id",
            "prescription",
            {"refillsLeft": 5, "lockedByStoreId": None},
        )

    @app.get("/prescriptions/<id>")
    def get_prescription(id):
        return read_item("prescriptions", id)

    @app.put("/prescriptions/<id>")
    def put_prescription(id):
        existing = stores["prescriptions"].get(id)
        result = update_item("prescriptions", "id", id)
        if existing is None:
            stores["prescriptions"][id].setdefault("refillsLeft", 5)
            stores["prescriptions"][id].setdefault("lockedByStoreId", None)
            return jsonify(stores["prescriptions"][id]), 200
        return result

    @app.delete("/prescriptions/<id>")
    def delete_prescription(id):
        return delete_item("prescriptions", id)

    @app.get("/inventory")
    def list_inventory():
        return list_items("inventory")

    @app.post("/inventory")
    def add_inventory():
        return create_item("inventory", "ndc", "inventory item")

    @app.get("/inventory/<ndc>")
    def get_inventory(ndc):
        return read_item("inventory", ndc)

    @app.put("/inventory/<ndc>")
    def put_inventory(ndc):
        return update_item("inventory", "ndc", ndc)

    @app.delete("/inventory/<ndc>")
    def delete_inventory(ndc):
        return delete_item("inventory", ndc)

    @app.post("/stores")
    def add_store():
        return create_item("pharmacy_stores", "storeId", "store")

    @app.get("/stores/<id>")
    def get_store(id):
        return read_item("pharmacy_stores", id)

    @app.post("/dispense")
    def dispense_drug():
        payload = request.get_json(silent=True)
        rx_id = payload["rxId"]
        prescription = stores["prescriptions"].get(rx_id)
        if prescription is None:
            return jsonify({"error": "Rx not found"}), 404
        remaining = prescription.get("refillsLeft", 5)
        if remaining <= 0:
            return jsonify({"error": "No refills left"}), 409
        prescription["refillsLeft"] = remaining - 1
        return jsonify({"status": "dispensed", "remaining": prescription["refillsLeft"]}), 201

    @app.post("/process-rx")
    def process_rx():
        payload = request.get_json(silent=True)
        rx_id = payload["rxId"]
        store_id = payload["storeId"]
        prescription = stores["prescriptions"].get(rx_id)
        if prescription is None:
            return jsonify({"error": "Rx not found"}), 404
        if store_id not in stores["pharmacy_stores"]:
            return jsonify({"error": "Store not found"}), 404
        current_store = prescription.get("lockedByStoreId")
        if current_store is not None and current_store != store_id:
            return jsonify({"error": "Prescription is assigned to another store"}), 409
        if current_store == store_id:
            return jsonify({"status": "processed", "store": store_id}), 200
        prescription["lockedByStoreId"] = store_id
        return jsonify({"status": "processed", "store": store_id}), 201

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
