import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import index as hosted_app
from app.hosted_engine import HostedEngine
from app.hosted_store import HostedStore


class Clock:
    def __init__(self, now=1000):
        self.now = now

    def __call__(self):
        return self.now


def packet(message_id, kind, event):
    return {
        'metadata': {'message_id': message_id},
        'payload': {'subscription': {'type': kind}, 'event': event},
    }


class HostedEngineTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix='.sqlite3')
        os.close(fd)
        self.store = HostedStore('sqlite:///' + self.path.replace('\\', '/'))
        self.clock = Clock()
        self.engine = HostedEngine(self.store, duration=45, clock=self.clock)

    def tearDown(self):
        self.store.engine.dispose()
        if os.path.exists(self.path):
            os.unlink(self.path)

    def raid(self, mid, broadcaster, raider='raider', viewers=12):
        return packet(mid, 'channel.raid', {
            'from_broadcaster_user_name': raider,
            'from_broadcaster_user_id': 'from-' + mid,
            'to_broadcaster_user_id': broadcaster,
            'viewers': viewers,
        })

    def chat(self, mid, broadcaster, chatter, emote=False):
        fragments = [{'type': 'text', 'text': 'W raid'}]
        if emote:
            fragments.append({'type': 'emote', 'text': 'Kappa', 'emote': {'id': '25'}})
        return packet(mid, 'channel.chat.message', {
            'broadcaster_user_id': broadcaster,
            'chatter_user_id': chatter,
            'chatter_user_name': chatter,
            'message': {'text': 'W raid', 'fragments': fragments},
        })

    def test_streamers_forge_independently(self):
        self.assertTrue(self.engine.apply(self.raid('r1', 'A', 'alpha')))
        self.assertTrue(self.engine.apply(self.raid('r2', 'B', 'beta')))
        self.engine.apply(self.chat('c1', 'A', 'alice', emote=True))
        self.engine.apply(self.chat('c2', 'B', 'bob'))
        a = self.engine.snapshot_sessions('A')[0]
        b = self.engine.snapshot_sessions('B')[0]
        self.assertEqual(a['raid']['from_broadcaster_user_name'], 'alpha')
        self.assertEqual(b['raid']['from_broadcaster_user_name'], 'beta')
        self.assertEqual(a['unique_chatters'], 1)
        self.assertEqual(b['unique_chatters'], 1)
        self.assertEqual(a['emotes'], 1)
        self.assertEqual(b['emotes'], 0)

    def test_duplicate_event_is_ignored(self):
        raid = self.raid('same', 'A')
        self.assertTrue(self.engine.apply(raid))
        self.assertFalse(self.engine.apply(raid))
        self.assertEqual(len(self.engine.snapshot_sessions('A')), 1)

    def test_polling_tick_archives_without_background_process(self):
        self.engine.apply(self.raid('r1', 'A'))
        self.clock.now += 46
        session = self.engine.snapshot_sessions('A')[0]
        self.assertEqual(session['phase'], 'ARCHIVED')
        self.assertIsNotNone(session['relic'])

    def test_archives_are_scoped_to_each_broadcaster(self):
        self.engine.apply(self.raid('r1', 'A', 'alpha'))
        self.engine.apply(self.raid('r2', 'B', 'beta'))
        self.clock.now += 46
        a = self.engine.snapshot_sessions('A')
        b = self.engine.snapshot_sessions('B')
        self.assertEqual([s['raid']['from_broadcaster_user_name'] for s in a], ['alpha'])
        self.assertEqual([s['raid']['from_broadcaster_user_name'] for s in b], ['beta'])
        self.assertTrue(all(s['broadcaster_id'] == 'A' for s in a))
        self.assertTrue(all(s['broadcaster_id'] == 'B' for s in b))

    def test_oauth_state_is_one_time_and_expires(self):
        state = self.store.create_oauth_state(ttl=10, now=100)
        self.assertTrue(self.store.consume_oauth_state(state, now=105))
        self.assertFalse(self.store.consume_oauth_state(state, now=106))
        expired = self.store.create_oauth_state(ttl=10, now=100)
        self.assertFalse(self.store.consume_oauth_state(expired, now=111))


class HostedOAuthTests(unittest.TestCase):
    def test_maintenance_endpoint_rejects_missing_secret(self):
        original_secret = os.environ.get('RAIDRELIC_MAINTENANCE_SECRET')
        try:
            os.environ['RAIDRELIC_MAINTENANCE_SECRET'] = 'maintenance-test-secret'
            client = TestClient(hosted_app.app)
            response = client.post('/internal/oauth-maintenance')
            self.assertEqual(response.status_code, 401)
        finally:
            if original_secret is None:
                os.environ.pop('RAIDRELIC_MAINTENANCE_SECRET', None)
            else:
                os.environ['RAIDRELIC_MAINTENANCE_SECRET'] = original_secret

    def test_error_callback_recovers_existing_session(self):
        fd, path = tempfile.mkstemp(suffix='.sqlite3')
        os.close(fd)
        replacement_store = HostedStore('sqlite:///' + path.replace('\\', '/'))
        original_store = hosted_app.store
        original_secret = os.environ.get('RAIDRELIC_SESSION_SECRET')
        try:
            hosted_app.store = replacement_store
            os.environ['RAIDRELIC_SESSION_SECRET'] = 'test-session-secret'
            replacement_store.upsert_streamer(
                twitch_user_id='streamer-1', login='streamer', display_name='Streamer',
                access_token_enc='encrypted-access', refresh_token_enc='encrypted-refresh')
            state = replacement_store.create_oauth_state(ttl=600)
            session = hosted_app.sign_session('streamer-1')
            client = TestClient(hosted_app.app)
            response = client.get(
                f'/auth/callback?state={state}&error=access_denied',
                cookies={'raidrelic_session': session, 'raidrelic_oauth': state},
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers['location'], '/')
        finally:
            hosted_app.store = original_store
            replacement_store.engine.dispose()
            if original_secret is None:
                os.environ.pop('RAIDRELIC_SESSION_SECRET', None)
            else:
                os.environ['RAIDRELIC_SESSION_SECRET'] = original_secret
            if os.path.exists(path):
                os.unlink(path)

    def test_refreshing_consumed_callback_recovers_existing_session(self):
        fd, path = tempfile.mkstemp(suffix='.sqlite3')
        os.close(fd)
        replacement_store = HostedStore('sqlite:///' + path.replace('\\', '/'))
        original_store = hosted_app.store
        original_secret = os.environ.get('RAIDRELIC_SESSION_SECRET')
        try:
            hosted_app.store = replacement_store
            os.environ['RAIDRELIC_SESSION_SECRET'] = 'test-session-secret'
            replacement_store.upsert_streamer(
                twitch_user_id='streamer-1', login='streamer', display_name='Streamer',
                access_token_enc='encrypted-access', refresh_token_enc='encrypted-refresh')
            session = hosted_app.sign_session('streamer-1')
            client = TestClient(hosted_app.app)
            response = client.get(
                '/auth/callback?state=already-consumed',
                cookies={'raidrelic_session': session},
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers['location'], '/')
        finally:
            hosted_app.store = original_store
            replacement_store.engine.dispose()
            if original_secret is None:
                os.environ.pop('RAIDRELIC_SESSION_SECRET', None)
            else:
                os.environ['RAIDRELIC_SESSION_SECRET'] = original_secret
            if os.path.exists(path):
                os.unlink(path)


class FakeVault:
    ready = True

    def decrypt(self, value):
        return {'enc-old-access': 'old-access', 'enc-old-refresh': 'old-refresh'}[value]

    def encrypt(self, value):
        return 'enc-' + value


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload
        self.text = str(payload)

    def json(self):
        return self.payload


class RefreshHTTP:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None, **kwargs):
        token = (headers or {}).get('Authorization', '')
        if token.endswith('old-access'):
            return FakeResponse(401, {'message': 'invalid access token'})
        return FakeResponse(200, {
            'client_id': 'client-id',
            'user_id': 'streamer-1',
            'login': 'streamer',
            'scopes': sorted(hosted_app.REQUIRED_SCOPES),
        })

    async def post(self, url, data=None, **kwargs):
        if (data or {}).get('grant_type') == 'refresh_token':
            return FakeResponse(200, {
                'access_token': 'new-access',
                'refresh_token': 'new-refresh',
                'scope': sorted(hosted_app.REQUIRED_SCOPES),
            })
        return FakeResponse(400, {'message': 'unexpected request'})


class HostedTokenLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_401_refresh_rotates_and_persists_both_tokens(self):
        fd, path = tempfile.mkstemp(suffix='.sqlite3')
        os.close(fd)
        replacement_store = HostedStore('sqlite:///' + path.replace('\\', '/'))
        original_store, original_vault = hosted_app.store, hosted_app.vault
        old_client_id = os.environ.get('TWITCH_CLIENT_ID')
        old_client_secret = os.environ.get('TWITCH_CLIENT_SECRET')
        try:
            hosted_app.store = replacement_store
            hosted_app.vault = FakeVault()
            os.environ['TWITCH_CLIENT_ID'] = 'client-id'
            os.environ['TWITCH_CLIENT_SECRET'] = 'client-secret'
            replacement_store.upsert_streamer(
                twitch_user_id='streamer-1', login='streamer', display_name='Streamer',
                access_token_enc='enc-old-access', refresh_token_enc='enc-old-refresh')
            replacement_store.set_oauth_health('streamer-1', 'valid', checked_at=0, next_check_at=0)
            streamer = replacement_store.get_streamer_by_id('streamer-1')
            with patch('index.httpx.AsyncClient', return_value=RefreshHTTP()):
                status = await hosted_app.maintain_user_authorization(streamer)
            self.assertEqual(status, 'valid')
            updated = replacement_store.get_streamer_by_id('streamer-1')
            self.assertEqual(updated.access_token_enc, 'enc-new-access')
            self.assertEqual(updated.refresh_token_enc, 'enc-new-refresh')
            self.assertEqual(replacement_store.oauth_status('streamer-1'), 'valid')
        finally:
            hosted_app.store, hosted_app.vault = original_store, original_vault
            replacement_store.engine.dispose()
            if old_client_id is None:
                os.environ.pop('TWITCH_CLIENT_ID', None)
            else:
                os.environ['TWITCH_CLIENT_ID'] = old_client_id
            if old_client_secret is None:
                os.environ.pop('TWITCH_CLIENT_SECRET', None)
            else:
                os.environ['TWITCH_CLIENT_SECRET'] = old_client_secret
            if os.path.exists(path):
                os.unlink(path)


if __name__ == '__main__':
    unittest.main()
