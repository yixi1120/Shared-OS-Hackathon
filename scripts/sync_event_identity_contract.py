"""Mechanical sync of the additive input schema and changed duplicate fixture."""
import json
from pathlib import Path

from sharedos_commerce_agent.models import InteractionTraceInput

ROOT = Path(__file__).resolve().parents[1]
schema = InteractionTraceInput.model_json_schema()
for name in ['docs/siqi/schemas.json', 'docs/guansheng/schemas.json', 'src/sharedos_commerce_agent/resources/interaction_contract_v1.json']:
    path = ROOT / name
    value = json.loads(path.read_text())
    value['input'] = schema
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
(ROOT / 'docs/guansheng/input.schema.json').write_text(json.dumps(schema, ensure_ascii=False, indent=2) + '\n')
path = ROOT / 'tests/fixtures/interaction_v1.json'
cases = json.loads(path.read_text())
case = next(c for c in cases if c['id'] == 'duplicate_event')
case['proof'] = 'Identical logical events count once, including evidence references and source counts.'
case['expected']['provenance_counts'] = {'self_reported': 4}
case['expected']['evidence_ids'] = ['e0', 'e1', 'e3', 'e4']
path.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + '\n')
