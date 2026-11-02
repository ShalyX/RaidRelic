"""Single-channel forge. SQLite stores snapshots and event IDs atomically."""
import hashlib
import json
import sqlite3
import time


def relic(seed):
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return {'seed': seed, 'hue': int(digest[:4], 16) % 360,
            'sides': 5 + int(digest[4:6], 16) % 5,
            'facets': [int(digest[i:i+2], 16) / 255 for i in range(6, 30, 2)]}


class Engine:
    def __init__(self, path, duration=45, clock=time.time):
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, received REAL);
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, data TEXT NOT NULL);''')
        self.duration, self.clock = duration, clock
        self.changed = lambda: None

    def sessions(self):
        return [json.loads(r[0]) for r in self.db.execute('SELECT data FROM sessions ORDER BY rowid DESC')]

    def current(self, source):
        return next((s for s in self.sessions() if s['source'] == source and s['phase'] == 'FORGING'), None)

    def save(self, s):
        self.db.execute('INSERT OR REPLACE INTO sessions VALUES(?,?)', (s['id'], json.dumps(s)))

    def apply(self, message, source='twitch'):
        meta, payload = message['metadata'], message['payload']
        kind, event = payload['subscription']['type'], payload['event']
        if kind not in ('channel.raid', 'channel.chat.message'):
            return False
        event_id = source + ':' + meta['message_id']
        now = self.clock()
        with self.db:
            if self.db.execute('SELECT 1 FROM events WHERE id=?', (event_id,)).fetchone():
                return False
            self.db.execute('INSERT INTO events VALUES(?,?)', (event_id, now))
            s = self.current(source)
            if kind == 'channel.raid':
                # A second raid must not destroy an unfinished relic.
                if s:
                    self.finish(s, 'superseded_by_raid')
                s = {'id': event_id, 'source': source, 'phase': 'FORGING', 'started_at': now,
                     'ends_at': now + self.duration, 'raid': event,
                     'messages': 0, 'participants': [], 'emotes': 0, 'charge': 0,
                     'recent_chat': [], 'last_chat_received_at': None, 'relic': None}
                self.save(s)
            elif s and event.get('broadcaster_user_id') == s['raid'].get('to_broadcaster_user_id'):
                if now >= s['ends_at']:
                    self.finish(s, 'timer')
                else:
                    s['messages'] += 1
                    uid = event['chatter_user_id']
                    if uid not in s['participants']:
                        s['participants'].append(uid)
                    emote_count = sum(f.get('type') == 'emote' for f in event['message']['fragments'])
                    s['emotes'] += emote_count
                    s['charge'] = min(100, s['messages']*5 + len(s['participants'])*3 + s['emotes']*2)
                    chat_item = {
                        'user': event.get('chatter_user_name') or event.get('chatter_user_login') or 'viewer',
                        'text': (event.get('message') or {}).get('text') or ''.join(
                            str(f.get('text') or '') for f in (event.get('message') or {}).get('fragments', [])),
                        'emotes': emote_count,
                        'received_at': now,
                    }
                    s.setdefault('recent_chat', []).append(chat_item)
                    s['recent_chat'] = s['recent_chat'][-7:]
                    s['last_chat_received_at'] = now
                    self.save(s)
        self.changed()
        return True

    def finish(self, s, reason):
        seed = f"{s['id']}:{s['messages']}:{len(s['participants'])}:{s['emotes']}"
        s.update(phase='ARCHIVED', completed_at=self.clock(), completion_reason=reason, relic=relic(seed))
        self.save(s)

    def tick(self):
        changed = False
        with self.db:
            for s in self.sessions():
                if s['phase'] == 'FORGING' and self.clock() >= s['ends_at']:
                    self.finish(s, 'timer')
                    changed = True
        if changed:
            self.changed()
