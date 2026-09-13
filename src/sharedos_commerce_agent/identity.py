"""Self-service service identities, not verified SharedNet principals."""
import hashlib
import secrets
import time
from uuid import uuid4

from fastapi import HTTPException


class IdentityStore:
    def __init__(self, ledger):
        self.ledger = ledger
        with ledger._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS api_agents (agent_id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL, created_at REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)')
            db.execute('CREATE TABLE IF NOT EXISTS api_rate_limits (scope TEXT PRIMARY KEY, window INTEGER NOT NULL, count INTEGER NOT NULL)')

    def limit(self, scope, maximum, seconds):
        window = int(time.time()) // seconds
        with self.ledger._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT window,count FROM api_rate_limits WHERE scope=?', (scope,)).fetchone()
            count = row['count'] if row and row['window'] == window else 0
            if count >= maximum:
                raise HTTPException(429, 'Rate limit exceeded', headers={'Retry-After': str(seconds)})
            db.execute('INSERT INTO api_rate_limits VALUES (?,?,?) ON CONFLICT(scope) DO UPDATE SET window=excluded.window,count=excluded.count', (scope, window, count + 1))

    def register(self, name):
        self.limit('registration', 100, 3600)
        agent_id, token = 'agt_' + uuid4().hex, 'sos_' + secrets.token_urlsafe(32)
        with self.ledger._connect() as db:
            db.execute('INSERT INTO api_agents(agent_id,name,token_hash,created_at) VALUES (?,?,?,?)',
                       (agent_id, name, hashlib.sha256(token.encode()).hexdigest(), time.time()))
        return {'agent_id': agent_id, 'buyer_id': agent_id, 'api_key': token,
                'token_type': 'Bearer', 'identity_verified': False,
                'credit_settlement': 'not_evaluated'}

    def authenticate(self, token):
        if len(token) > 256:
            return None
        with self.ledger._connect() as db:
            row = db.execute('SELECT agent_id FROM api_agents WHERE token_hash=? AND revoked=0',
                             (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        return row['agent_id'] if row else None

    def has_agents(self):
        with self.ledger._connect() as db:
            return db.execute('SELECT 1 FROM api_agents LIMIT 1').fetchone() is not None

    def revoke(self, agent_id):
        with self.ledger._connect() as db:
            db.execute('UPDATE api_agents SET revoked=1 WHERE agent_id=?', (agent_id,))
