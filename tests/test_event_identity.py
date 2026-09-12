from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from sharedos_commerce_agent.api import create_app
from sharedos_commerce_agent.config import Settings
from sharedos_commerce_agent.event_identity import EventConflictError, deduplicate_events, identity
from sharedos_commerce_agent.ledger import Ledger
from sharedos_commerce_agent.models import InteractionEvent
from sharedos_commerce_agent.sharednet_adapter import SharedNetRoomClient, SharedNetProtocolError
from sharedos_commerce_agent.telemetry import evaluate_interaction_trace


def sample():
    cases = json.loads((Path(__file__).parent / 'fixtures/interaction_v1.json').read_text())
    raw = next(c['events'] for c in cases if c['id'] == 'partial_schema')
    return [InteractionEvent.model_validate({**e, 'event_id': f'event-{i}', 'source_id': 'trusted-node-1'}) for i, e in enumerate(raw)]


@pytest.mark.parametrize('valid', [True, False])
@pytest.mark.parametrize('copies', [1, 20])
def test_explicit_replays_preserve_all_metrics(valid, copies):
    events = sample()
    duplicate = next(e for e in events if e.schema_valid == valid)
    original = evaluate_interaction_trace(events)
    assert original.execution_score == 93
    assert evaluate_interaction_trace(events + [duplicate] * copies) == original


def test_different_ids_are_distinct_and_sources_tasks_subjects_are_scoped():
    event = sample()[0]
    for field, value in [('event_id', 'different'), ('source_id', 'node-2'), ('task_id', 'task-2'), ('subject_agent_id', 'agent-2')]:
        assert len(deduplicate_events([event, event.model_copy(update={field: value})])) == 2


def test_conflict_fails_before_analysis_and_logs_only_hashes(caplog):
    event = sample()[0]
    with pytest.raises(EventConflictError):
        evaluate_interaction_trace([event, event.model_copy(update={'schema_valid': False})])
    assert 'event_identity_conflict key_hash=' in caplog.text
    assert event.source_id not in caplog.text


def test_normalization_legacy_compatibility_and_empty_id():
    event = sample()[0]
    raw = event.model_dump(mode='json')
    raw['occurred_at'] = '2026-09-10T08:00:00+08:00'
    assert identity(event) == identity(InteractionEvent.model_validate(raw))
    legacy = event.model_copy(update={'event_id': None})
    assert len(deduplicate_events([legacy, legacy])) == 1
    with pytest.raises(ValueError):
        InteractionEvent.model_validate({**raw, 'event_id': ''})


def test_registry_restart_conflict_audit_and_atomic_batch(tmp_path):
    path = str(tmp_path / 'events.sqlite')
    event = sample()[0]
    Ledger(path).validate_events([event])
    restored = Ledger(path)
    assert restored.validate_events([event, event]) == [event]
    fresh = event.model_copy(update={'event_id': 'fresh'})
    with pytest.raises(EventConflictError):
        restored.validate_events([fresh, event.model_copy(update={'schema_valid': False})])
    audit = Ledger(path).event_conflicts()
    assert len(audit) == 1 and audit[0]['previous_hash'] != audit[0]['incoming_hash']
    # Rejected batch must not register its earlier, otherwise valid event.
    assert restored.validate_events([fresh.model_copy(update={'schema_valid': False})])


def test_two_connections_cannot_overwrite_identity(tmp_path):
    path = str(tmp_path / 'events.sqlite')
    ledgers = [Ledger(path), Ledger(path)]
    event = sample()[0]
    def attempt(index):
        try:
            ledgers[index].validate_events([event.model_copy(update={'schema_valid': bool(index)})])
            return 'accepted'
        except EventConflictError:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == ['accepted', 'conflict']


def test_public_conflict_is_409_persisted_and_spoofed_source_does_not_bypass(tmp_path):
    path = str(tmp_path / 'api.sqlite')
    events = [e.model_dump(mode='json') for e in sample()]
    with TestClient(create_app(Settings(ledger_path=path))) as client:
        service = 'a2a-interaction-trace'
        quote = client.post('/v1/quotes', json=dict(buyer_id='b', service_id=service, budget=6)).json()
        payload = dict(quote_id=quote['quote_id'], buyer_id='b', service_id=service, amount=6, idempotency_key='dedup-order-1', input={'events': events + [events[0]]})
        order = client.post('/v1/orders', json=payload)
        assert order.status_code == 200
        payload['input']['events'] = events
        assert client.post('/v1/orders', json=payload).json()['trade_id'] == order.json()['trade_id']
        assert client.post('/v1/orders/' + order.json()['trade_id'] + '/deliver').json()['output']['execution_score'] == 93
        payload['idempotency_key'] = 'dedup-order-2'
        payload['input']['events'] = [{**events[0], 'schema_valid': False, 'source_id': 'spoof', 'provenance': 'platform'}]
        response = client.post('/v1/orders', json=payload)
        assert response.status_code == 409
        assert 'event_identity_conflict' in response.json()['detail']
    assert len(Ledger(path).event_conflicts()) == 1
    assert len(Ledger(path).list()) == 1


async def test_room_message_replay_ack_and_restart_are_separate_from_events(tmp_path):
    path = str(tmp_path / 'inbox.sqlite')
    message = dict(id='msg-1', sequence=1, content='same business event', sender_instance_id='sender')
    calls = []
    def handler(request):
        calls.append(request.url.params['after'])
        return httpx.Response(200, json={'items': [message, message], 'next_cursor': 1})
    async with SharedNetRoomClient(room_id='rom_test', member_token='sni_test', transport=httpx.MockTransport(handler)) as client:
        pending = await client.receive_pending(Ledger(path), timeout_seconds=0)
        assert len(pending) == 1
        # Restart without ack retries pending work without another network fetch.
        assert await client.receive_pending(Ledger(path), timeout_seconds=0) == pending
        assert calls == ['0']
        Ledger(path).acknowledge_message('rom_test', 'msg-1')
        assert await client.receive_pending(Ledger(path), timeout_seconds=0) == ()
        assert calls == ['0', '1']
        # Different room has its own identity scope.
        other = Ledger(path)
        other.receive_messages('rom_other', [dict(message_id='msg-1', sequence=1, content='other')], 1)
        assert len(other.pending_messages('rom_other')) == 1


async def test_room_missing_or_changed_id_rejects_without_cursor_commit(tmp_path):
    inbox = Ledger(str(tmp_path / 'inbox.sqlite'))
    message = dict(id='msg-1', sequence=1, content='original')
    def handler(request):
        return httpx.Response(200, json={'items': [message], 'next_cursor': 2})
    async with SharedNetRoomClient(room_id='rom_test', member_token='sni_test', transport=httpx.MockTransport(handler)) as client:
        await client.receive_pending(inbox, timeout_seconds=0)
        inbox.acknowledge_message('rom_test', 'msg-1')
        message['content'] = 'changed'
        with pytest.raises(SharedNetProtocolError, match='conflict'):
            await client.receive_pending(inbox, timeout_seconds=0)
        assert inbox.message_cursor('rom_test') == 2
        message.pop('id')
        with pytest.raises(SharedNetProtocolError, match='message_id'):
            await client.receive_pending(inbox, timeout_seconds=0)
