import json
import os
import secrets
import time
from dataclasses import dataclass

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text


def _database_url():
    raw = os.getenv('DATABASE_URL') or os.getenv('RAIDRELIC_DATABASE_URL')
    if not raw:
        if os.getenv('VERCEL'):
            return 'sqlite:////tmp/raidrelic-hosted-dev.sqlite3'
        return 'sqlite:///hosted-dev.sqlite3'
    if raw.startswith('postgres://'):
        raw = 'postgresql://' + raw[len('postgres://'):]
    if raw.startswith('postgresql://'):
        raw = 'postgresql+psycopg://' + raw[len('postgresql://'):]
    return raw


def storage_is_durable():
    return bool(os.getenv('DATABASE_URL') or os.getenv('RAIDRELIC_DATABASE_URL'))


@dataclass
class Streamer:
    twitch_user_id: str
    login: str
    display_name: str
    overlay_key: str
    access_token_enc: str
    refresh_token_enc: str
    subscriptions: list


class TokenVault:
    def __init__(self):
        key = os.getenv('RAIDRELIC_TOKEN_KEY', '').encode()
        self.fernet = Fernet(key) if key else None

    @property
    def ready(self):
        return self.fernet is not None

    def encrypt(self, value):
        if not self.fernet:
            raise RuntimeError('RAIDRELIC_TOKEN_KEY is not configured.')
        return self.fernet.encrypt((value or '').encode()).decode()

    def decrypt(self, value):
        if not self.fernet:
            raise RuntimeError('RAIDRELIC_TOKEN_KEY is not configured.')
        return self.fernet.decrypt((value or '').encode()).decode()


class HostedStore:
    def __init__(self, url=None):
        url = url or _database_url()
        kwargs = {'future': True, 'pool_pre_ping': True}
        if url.startswith('sqlite:'):
            kwargs['connect_args'] = {'check_same_thread': False}
        self.engine = create_engine(url, **kwargs)
        self.init_schema()

    def init_schema(self):
        ddl = [
            '''CREATE TABLE IF NOT EXISTS streamers (
                twitch_user_id TEXT PRIMARY KEY,
                login TEXT NOT NULL,
                display_name TEXT NOT NULL,
                overlay_key TEXT NOT NULL UNIQUE,
                access_token_enc TEXT NOT NULL,
                refresh_token_enc TEXT NOT NULL,
                subscriptions_json TEXT NOT NULL DEFAULT '[]',
                connected_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )''',
            '''CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                broadcaster_id TEXT NOT NULL,
                received REAL NOT NULL
            )''',
            '''CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                broadcaster_id TEXT NOT NULL,
                source TEXT NOT NULL,
                phase TEXT NOT NULL,
                data TEXT NOT NULL,
                updated_at REAL NOT NULL
            )''',
            '''CREATE TABLE IF NOT EXISTS oauth_states (
                state TEXT PRIMARY KEY,
                expires_at REAL NOT NULL
            )''',
            '''CREATE TABLE IF NOT EXISTS oauth_health (
                twitch_user_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'valid',
                last_checked_at REAL NOT NULL DEFAULT 0,
                next_check_at REAL NOT NULL DEFAULT 0
            )''',
            'CREATE INDEX IF NOT EXISTS idx_sessions_broadcaster ON sessions(broadcaster_id, updated_at)',
            'CREATE INDEX IF NOT EXISTS idx_sessions_phase ON sessions(broadcaster_id, phase)',
        ]
        with self.engine.begin() as conn:
            for statement in ddl:
                conn.execute(text(statement))

    def create_oauth_state(self, ttl=600, now=None):
        now = time.time() if now is None else now
        state = secrets.token_urlsafe(32)
        with self.engine.begin() as conn:
            conn.execute(text('DELETE FROM oauth_states WHERE expires_at < :now'), {'now': now})
            conn.execute(text('INSERT INTO oauth_states(state, expires_at) VALUES(:state, :expires)'), {
                'state': state, 'expires': now + ttl})
        return state

    def consume_oauth_state(self, state, now=None):
        if not state:
            return False
        now = time.time() if now is None else now
        with self.engine.begin() as conn:
            result = conn.execute(text('DELETE FROM oauth_states WHERE state=:state AND expires_at >= :now'), {
                'state': state, 'now': now})
            conn.execute(text('DELETE FROM oauth_states WHERE expires_at < :now'), {'now': now})
        return result.rowcount == 1

    def upsert_streamer(self, twitch_user_id, login, display_name, access_token_enc, refresh_token_enc):
        now = time.time()
        with self.engine.begin() as conn:
            row = conn.execute(text('SELECT overlay_key, subscriptions_json FROM streamers WHERE twitch_user_id=:id'), {'id': twitch_user_id}).mappings().first()
            overlay_key = row['overlay_key'] if row else secrets.token_urlsafe(24)
            subscriptions = row['subscriptions_json'] if row else '[]'
            conn.execute(text('''INSERT INTO streamers
                (twitch_user_id, login, display_name, overlay_key, access_token_enc, refresh_token_enc, subscriptions_json, connected_at, updated_at)
                VALUES (:id,:login,:display,:overlay,:access,:refresh,:subs,:now,:now)
                ON CONFLICT(twitch_user_id) DO UPDATE SET
                    login=excluded.login,
                    display_name=excluded.display_name,
                    access_token_enc=excluded.access_token_enc,
                    refresh_token_enc=excluded.refresh_token_enc,
                    updated_at=excluded.updated_at'''), {
                'id': twitch_user_id, 'login': login, 'display': display_name or login,
                'overlay': overlay_key, 'access': access_token_enc, 'refresh': refresh_token_enc,
                'subs': subscriptions, 'now': now,
            })
        return self.get_streamer_by_id(twitch_user_id)

    def _streamer(self, row):
        if not row:
            return None
        return Streamer(
            twitch_user_id=row['twitch_user_id'], login=row['login'], display_name=row['display_name'],
            overlay_key=row['overlay_key'], access_token_enc=row['access_token_enc'],
            refresh_token_enc=row['refresh_token_enc'], subscriptions=json.loads(row['subscriptions_json'] or '[]'))

    def get_streamer_by_id(self, twitch_user_id):
        with self.engine.connect() as conn:
            row = conn.execute(text('SELECT * FROM streamers WHERE twitch_user_id=:id'), {'id': twitch_user_id}).mappings().first()
        return self._streamer(row)

    def get_streamer_by_overlay(self, overlay_key):
        with self.engine.connect() as conn:
            row = conn.execute(text('SELECT * FROM streamers WHERE overlay_key=:key'), {'key': overlay_key}).mappings().first()
        return self._streamer(row)

    def set_subscriptions(self, twitch_user_id, subscriptions):
        with self.engine.begin() as conn:
            conn.execute(text('UPDATE streamers SET subscriptions_json=:subs, updated_at=:now WHERE twitch_user_id=:id'), {
                'subs': json.dumps(sorted(set(subscriptions))), 'now': time.time(), 'id': twitch_user_id})

    def update_tokens(self, twitch_user_id, access_token_enc, refresh_token_enc):
        with self.engine.begin() as conn:
            conn.execute(text('''UPDATE streamers SET access_token_enc=:access, refresh_token_enc=:refresh,
                updated_at=:now WHERE twitch_user_id=:id'''), {
                'access': access_token_enc, 'refresh': refresh_token_enc,
                'now': time.time(), 'id': twitch_user_id})

    def set_oauth_health(self, twitch_user_id, status='valid', checked_at=None, next_check_at=None):
        checked_at = time.time() if checked_at is None else checked_at
        next_check_at = checked_at + 3600 if next_check_at is None else next_check_at
        with self.engine.begin() as conn:
            conn.execute(text('''INSERT INTO oauth_health(twitch_user_id,status,last_checked_at,next_check_at)
                VALUES(:id,:status,:checked,:next)
                ON CONFLICT(twitch_user_id) DO UPDATE SET
                    status=excluded.status,
                    last_checked_at=excluded.last_checked_at,
                    next_check_at=excluded.next_check_at'''), {
                'id': twitch_user_id, 'status': status, 'checked': checked_at, 'next': next_check_at})

    def oauth_status(self, twitch_user_id):
        with self.engine.connect() as conn:
            row = conn.execute(text('SELECT status FROM oauth_health WHERE twitch_user_id=:id'), {'id': twitch_user_id}).first()
        return row[0] if row else 'valid'

    def claim_oauth_check(self, twitch_user_id, now=None, lease=60):
        now = time.time() if now is None else now
        with self.engine.begin() as conn:
            conn.execute(text('''INSERT INTO oauth_health(twitch_user_id,status,last_checked_at,next_check_at)
                VALUES(:id,'valid',0,0) ON CONFLICT(twitch_user_id) DO NOTHING'''), {'id': twitch_user_id})
            result = conn.execute(text('''UPDATE oauth_health SET status='checking', next_check_at=:lease_until
                WHERE twitch_user_id=:id AND next_check_at<=:now'''), {
                'id': twitch_user_id, 'now': now, 'lease_until': now + lease})
        return result.rowcount == 1

    def remember_event(self, event_id, broadcaster_id):
        with self.engine.begin() as conn:
            exists = conn.execute(text('SELECT 1 FROM events WHERE id=:id'), {'id': event_id}).first()
            if exists:
                return False
            conn.execute(text('INSERT INTO events(id,broadcaster_id,received) VALUES(:id,:b,:now)'), {
                'id': event_id, 'b': broadcaster_id, 'now': time.time()})
        return True

    def save_session(self, session):
        now = time.time()
        with self.engine.begin() as conn:
            conn.execute(text('''INSERT INTO sessions(id,broadcaster_id,source,phase,data,updated_at)
                VALUES(:id,:b,:source,:phase,:data,:now)
                ON CONFLICT(id) DO UPDATE SET
                    broadcaster_id=excluded.broadcaster_id,
                    source=excluded.source,
                    phase=excluded.phase,
                    data=excluded.data,
                    updated_at=excluded.updated_at'''), {
                'id': session['id'], 'b': session['broadcaster_id'], 'source': session['source'],
                'phase': session['phase'], 'data': json.dumps(session), 'now': now})

    def sessions(self, broadcaster_id, limit=50):
        with self.engine.connect() as conn:
            rows = conn.execute(text('''SELECT data FROM sessions WHERE broadcaster_id=:b
                ORDER BY updated_at DESC LIMIT :limit'''), {'b': broadcaster_id, 'limit': limit}).all()
        return [json.loads(row[0]) for row in rows]

    def current_session(self, broadcaster_id):
        with self.engine.connect() as conn:
            row = conn.execute(text('''SELECT data FROM sessions WHERE broadcaster_id=:b AND phase='FORGING'
                ORDER BY updated_at DESC LIMIT 1'''), {'b': broadcaster_id}).first()
        return json.loads(row[0]) if row else None
