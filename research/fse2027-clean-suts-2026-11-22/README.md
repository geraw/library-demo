# Clean typed Garage and Pharmacy SUT baselines

This directory preserves clean baseline implementations and their OpenAPI 3.0 contracts for the FSE 2027 REST testing study. The two systems are kept free of seeded experimental faults so that later mutant variants can be added separately.

## Contents

- `garage/garage_sut.py`: standalone Garage service, with its request type validator and OpenAPI request schemas embedded in the source.
- `garage/openapi.json`: external contract for test-generation tools and inspection.
- `pharmacy/app.py`: standalone Pharmacy service, with its request type validator and OpenAPI request schemas embedded in the source.
- `pharmacy/openapi.json`: external contract for test-generation tools and inspection.
- `run_garage.py` and `run_pharmacy.py`: launchers for ports 5001 and 5002.
- `requirements.txt`: Python runtime dependencies.
- `WHATSAPP_UPDATE_HE.md`: prepared team update; it has not been sent.
- `source_manifest.json` and `SHA256SUMS`: source provenance and integrity data.

## API coverage

Garage has 33 operations: the 32 operations from the FSE artifact API plus `/reset`.

Pharmacy has 30 operations: the 29 operations from the full FSE artifact API plus `/reset`. This Pharmacy service is a clean reconstruction that combines the supplied CRUD/type-check implementation with the missing operations from the complete API. It is not claimed to be byte-for-byte identical to the historical Pharmacy SUT used in earlier paper runs.

## Standalone behavior and type checks

Each SUT file embeds the schema document and validator it needs. The service can start without a neighboring `openapi.json` file and without importing a shared `type_validation.py` module. The separate JSON contract remains available for tools such as EvoMaster and RESTler.

Before a JSON request reaches its route handler, the validator checks JSON content type, valid JSON, schema types, required properties, enums, references, and supported bounds. Boolean values are not accepted as integers. The contracts preserve extensible fields where `additionalProperties` is enabled.

## Reproduce locally

From this directory, create and activate a virtual environment, then install the listed dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Start Garage in one terminal:

```powershell
python run_garage.py
```

Start Pharmacy in another terminal:

```powershell
python run_pharmacy.py
```

Garage listens at `http://127.0.0.1:5001`; Pharmacy listens at `http://127.0.0.1:5002`. Each service exposes `/reset`.

## Validation and limitations

Packaging checks parsed both SUT files as Python and confirmed that each embeds the same OpenAPI document as its separate JSON contract. The source files have no runtime dependency on `type_validation.py` or `openapi.json`. HTTP server execution was not performed in this packaging environment; install `requirements.txt` and run the services before using them in a new experiment.

The Garage implementation is based on the clean Garage source in the FSE 2027 artifact release candidate v3.8. The Pharmacy implementation is the documented clean reconstruction above. The original FSE archive SHA-256 is recorded in `source_manifest.json`.
