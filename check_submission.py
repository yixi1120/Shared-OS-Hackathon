"""Check confirmed submission data without publishing or inventing values."""
import json
from pathlib import Path

REQUIRED = ('discord_username', 'discord_submission_channel', 'sharednet_seat_id',
            'sharedos_principal_id', 'sharedos_agent_address', 'service_base_url', 'sharednet_node_id', 'purpose_string')

def missing_fields(data):
    return [name for name in REQUIRED if not isinstance(data.get(name), str) or not data[name].strip()]

if __name__ == '__main__':
    data = json.loads((Path(__file__).parent / 'docs/guansheng/submission.json').read_text(encoding='utf-8'))
    missing = missing_fields(data)
    print(json.dumps({'ready_to_prepare_submission': not missing, 'missing_fields': missing,
                      'submitted': bool(data.get('discord_submission_message_url') and data.get('submitted_at'))}, indent=2))
    raise SystemExit(1 if missing else 0)
