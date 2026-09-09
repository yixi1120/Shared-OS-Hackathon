"""Local completeness check only; never submits or authenticates evidence."""
from pathlib import Path
import json

path=Path(__file__).resolve().parents[1]/'docs/guansheng/release.json'
data=json.loads(path.read_text(encoding='utf-8'))
required=('team_lead_discord','sharednet_node_id','sharedos_purpose','product_agent_addresses',
          'sharednet_service_address','confirmed_deadline','confirmed_arena_start','confirmed_arena_end',
          'repository_has_deliverable_code','pricing_reconciled','runtime_authorization_verified',
          'external_call_receipt','cloud_audit_reference','two_hour_soak_report')
missing=[key for key in required if not data.get(key)]
print(json.dumps({'ready_for_review':not missing,'missing':missing,
                  'note':'Completeness only; each item needs actual evidence. No submission performed.'},ensure_ascii=False,indent=2))
raise SystemExit(2 if missing else 0)
