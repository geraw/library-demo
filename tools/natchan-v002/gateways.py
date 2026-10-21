"""Independent, versioned tool and product gateways for retained evidence."""
from dataclasses import dataclass
from typing import Protocol


class ToolGateway(Protocol):
    id: str
    def normalize(self, label: str, record: dict) -> dict: ...


class ProductGateway(Protocol):
    id: str
    def describe(self, record: dict) -> dict: ...


@dataclass(frozen=True)
class RecordedToolGateway:
    """Decode the common recorded envelope; opaque native formats stay opaque."""
    id: str = 'recorded-json-v1'

    def normalize(self, label, record):
        role = record.get('role')
        kind = ('execution' if label == 'execution_json' else 'native_record' if label == 'native_jsonl'
                else 'imported_claim' if role == 'verdict' else 'boundary' if role == 'boundary'
                else 'http' if 'method' in record and ('path' in record or 'model_path' in record)
                else 'observation')
        return dict(kind=kind, role=role or 'unknown',
                    native_interpretation='not_evaluated', gateway=self.id)


@dataclass(frozen=True)
class ProvengoFixedJavaGateway(RecordedToolGateway):
    id: str = 'provengo-fixed-java-v011'

    def normalize(self, label, record):
        value = super().normalize(label, record)
        if label == 'native_jsonl' and type(record.get('native_pass')) is bool:
            value['native_interpretation'] = 'recorded_test_verdict'
            value['native_metric'] = 'test_pass_boolean'
            value['native_value'] = record['native_pass']
        return value


@dataclass(frozen=True)
class OpaqueProductGateway:
    id: str = 'opaque-product-v1'

    def describe(self, record):
        return dict(gateway=self.id, operation=None, entities=[], rules=[],
                    status='unmapped', reason='No product mapping selected')


@dataclass(frozen=True)
class LibraryProductGateway:
    id: str = 'library-issta-v006'

    def describe(self, record):
        # Use recorded API path and explicit fixture catalog; no inferred business semantics.
        from urllib.parse import urlsplit
        path = record.get('path', record.get('model_path'))
        if not isinstance(path, str) or not isinstance(record.get('method'), str):
            return dict(gateway=self.id, operation=None, entities=[], rules=[], status='not_http')
        parts = urlsplit(path).path.strip('/').split('/')
        resource = parts[0] if parts else ''
        if resource not in ('users', 'books', 'loans', 'holds') or len(parts) > 2:
            return dict(gateway=self.id, operation=None, entities=[], rules=[], status='unmapped')
        return dict(gateway=self.id, operation=record['method'].upper() + ' /' + resource + ('/{id}' if len(parts)==2 else ''),
                    entities=[dict(resource=resource, path_id=parts[1] if len(parts)==2 else None)],
                    rules=[], status='mapped',
                    rule_provider='tools/semantic-checker-v001:library-issta-v006',
                    note='Rules remain in the preserved evaluator; not executed by ingestion')


TOOLS = {'recorded-json-v1': RecordedToolGateway(),
         'provengo-fixed-java-v011': ProvengoFixedJavaGateway()}
PRODUCTS = {'opaque-product-v1': OpaqueProductGateway(),
            'library-issta-v006': LibraryProductGateway()}


def select(run):
    """Selection is explicit and independent of tool/product display labels."""
    tool_id = run.get('tool_gateway', 'recorded-json-v1')
    product_id = run.get('product_gateway', 'opaque-product-v1')
    if tool_id not in TOOLS or product_id not in PRODUCTS:
        raise ValueError('Unsupported gateway: ' + str((tool_id, product_id)))
    return TOOLS[tool_id], PRODUCTS[product_id]
