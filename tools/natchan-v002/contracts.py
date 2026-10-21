"""Gateway API v1: declared abilities, evidence requirements and output checks."""
from dataclasses import dataclass

API_VERSION = 'natchan-gateway/1'


@dataclass(frozen=True)
class GatewayContract:
    dimension: str
    capabilities: tuple
    required_artifacts: tuple = ()
    optional_artifacts: tuple = ()
    evidence_requirements: tuple = ()
    limitations: tuple = ()

    def export(self, gateway_id):
        if self.dimension not in ('tool', 'product'):
            raise ValueError('Invalid gateway dimension')
        return dict(api_version=API_VERSION, id=gateway_id, dimension=self.dimension,
                    capabilities=list(self.capabilities), required_artifacts=list(self.required_artifacts),
                    optional_artifacts=list(self.optional_artifacts),
                    evidence_requirements=list(self.evidence_requirements), limitations=list(self.limitations))


def describe_contract(gateway, dimension):
    if not isinstance(getattr(gateway, 'contract', None), GatewayContract):
        raise ValueError('Gateway must declare a GatewayContract')
    value = gateway.contract.export(gateway.id)
    if value['dimension'] != dimension:
        raise ValueError('Gateway contract dimension mismatch')
    if not isinstance(gateway.id, str) or not gateway.id:
        raise ValueError('Gateway id must be nonempty')
    if not callable(getattr(gateway, 'normalize' if dimension == 'tool' else 'describe', None)):
        raise ValueError('Gateway method missing')
    return value


def validate_tool_output(value, gateway_id):
    if not isinstance(value, dict) or value.get('gateway') != gateway_id:
        raise ValueError('Tool gateway output identity mismatch')
    allowed = {'kind','role','gateway','native_interpretation','native_metric','native_value'}
    if set(value) - allowed:
        raise ValueError('Tool gateway returned unsupported envelope fields')
    if value.get('kind') not in ('execution','native_record','imported_claim','boundary','http','observation'):
        raise ValueError('Invalid tool event kind')
    if not isinstance(value.get('role'), str):
        raise ValueError('Tool role must be a string')
    if not isinstance(value.get('native_interpretation'), str):
        raise ValueError('Tool native_interpretation must be explicit')


def validate_product_output(value, gateway_id):
    if not isinstance(value, dict) or value.get('gateway') != gateway_id:
        raise ValueError('Product gateway output identity mismatch')
    if value.get('status') not in ('mapped','unmapped','not_http'):
        raise ValueError('Invalid product mapping status')
    if not isinstance(value.get('entities'), list) or not isinstance(value.get('rules'), list):
        raise ValueError('Product entities and rules must be arrays')
    if value.get('operation') is not None and not isinstance(value['operation'], str):
        raise ValueError('Product operation must be string or null')


def evidence_availability(record, kind):
    """Observable presence only; never qualifies correctness or authorization."""
    if kind != 'http':
        return dict(status='not_applicable', missing=[])
    missing = []
    if not isinstance(record.get('method'), str): missing.append('method')
    if not isinstance(record.get('path', record.get('model_path')), str): missing.append('path')
    if type(record.get('status')) is not int: missing.append('status')
    if 'response' not in record: missing.append('response')
    return dict(status='partial' if missing else 'recorded', missing=missing,
                note='Presence only; a recorded null body is not a complete state readback')
