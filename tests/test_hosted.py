import os
import tempfile
import unittest

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

    def test_oauth_state_is_one_time_and_expires(self):
        state = self.store.create_oauth_state(ttl=10, now=100)
        self.assertTrue(self.store.consume_oauth_state(state, now=105))
        self.assertFalse(self.store.consume_oauth_state(state, now=106))
        expired = self.store.create_oauth_state(ttl=10, now=100)
        self.assertFalse(self.store.consume_oauth_state(expired, now=111))


class HostedOAuthTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
