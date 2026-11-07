"""Independent, versioned tool and product gateways for retained evidence."""
from dataclasses import dataclass
from typing import Protocol
from contracts import GatewayContract, describe_contract


class ToolGateway(Protocol):
    id: str
    contract: GatewayContract
    def normalize(self, label: str, record: dict) -> dict: ...


class ProductGateway(Protocol):
    id: str
    contract: GatewayContract
    def describe(self, record: dict) -> dict: ...


@dataclass(frozen=True)
class RecordedToolGateway:
    """Decode the common recorded envelope; opaque native formats stay opaque."""
    id: str = 'recorded-json-v1'
    contract = GatewayContract('tool', ('recorded_json', 'recorded_http', 'execution_metadata'),
        optional_artifacts=('trace','native_jsonl','execution_json'),
        evidence_requirements=('Exact source member and record location',),
        limitations=('No native format interpretation', 'No boundary reconstruction', 'No semantic verdicts'))

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
    contract = GatewayContract('tool', ('recorded_json','recorded_http','execution_metadata','native_test_verdict'),
        required_artifacts=('native_jsonl',), optional_artifacts=('trace','execution_json'),
        evidence_requirements=('native_pass must be boolean; case must identify the recorded test',),
        limitations=('Fixed Java v011 format only', 'Failed tests are not unique bugs'))

    def normalize(self, label, record):
        value = super().normalize(label, record)
        if label == 'native_jsonl' and type(record.get('native_pass')) is bool and type(record.get('case')) in (str, int):
            value['native_interpretation'] = 'recorded_test_verdict'
            value['native_metric'] = 'test_pass_boolean'
            value['native_value'] = record['native_pass']
        return value


@dataclass(frozen=True)
class OpaqueProductGateway:
    id: str = 'opaque-product-v1'
    contract = GatewayContract('product', (), limitations=('No operation, identity, state or rule mapping',))

    def describe(self, record):
        return dict(gateway=self.id, operation=None, entities=[], rules=[],
                    status='unmapped', reason='No product mapping selected')


@dataclass(frozen=True)
class LibraryProductGateway:
    id: str = 'library-issta-v006'
    contract = GatewayContract('product', ('operation_mapping','resource_path_mapping','rule_provider_reference','semantic_evaluation'),
        required_artifacts=('trace',), evidence_requirements=('Recorded public API method and path',
        'State/rule evaluation requires identity-bound responses and case boundaries in the later evaluator'),
        limitations=('Semantic evaluation delegates to preserved case-local Library checker', 'Path IDs are unverified lexical IDs'))

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


    def evaluate(self, events, artifact):
        from library_bridge import evaluate
        return evaluate(events, artifact)


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
    pair = TOOLS[tool_id], PRODUCTS[product_id]
    describe_contract(pair[0], 'tool')
    describe_contract(pair[1], 'product')
    return pair


def catalog():
    """Machine-readable negotiation catalog; no product/tool pairing table."""
    return dict(api_version='natchan-gateway/1',
                tools=[describe_contract(g, 'tool') for g in TOOLS.values()],
                products=[describe_contract(g, 'product') for g in PRODUCTS.values()])


if __name__ == '__main__':
    import json
    print(json.dumps(catalog(), indent=2))
