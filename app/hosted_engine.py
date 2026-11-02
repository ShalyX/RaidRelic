import time

from app.engine import relic


class HostedEngine:
    def __init__(self, store, duration=45, clock=time.time):
        self.store = store
        self.duration = duration
        self.clock = clock

    @staticmethod
    def broadcaster_id(packet):
        payload = packet.get('payload') or packet
        subscription = payload.get('subscription') or {}
        event = payload.get('event') or {}
        kind = subscription.get('type')
        if kind == 'channel.raid':
            return event.get('to_broadcaster_user_id') or subscription.get('condition', {}).get('to_broadcaster_user_id')
        if kind == 'channel.chat.message':
            return event.get('broadcaster_user_id') or subscription.get('condition', {}).get('broadcaster_user_id')
        return None

    def apply(self, packet, source='twitch'):
        payload = packet.get('payload') or packet
        subscription = payload.get('subscription') or {}
        event = payload.get('event') or {}
        kind = subscription.get('type')
        if kind not in ('channel.raid', 'channel.chat.message'):
            return False
        broadcaster_id = self.broadcaster_id(packet)
        if not broadcaster_id:
            return False
        message_id = (packet.get('metadata') or {}).get('message_id') or packet.get('message_id')
        if not message_id:
            return False
        event_id = f'{source}:{message_id}'
        if not self.store.remember_event(event_id, broadcaster_id):
            return False

        now = self.clock()
        session = self.store.current_session(broadcaster_id)
        if kind == 'channel.raid':
            if session:
                self.finish(session, 'superseded_by_raid')
            session = {
                'id': event_id,
                'broadcaster_id': broadcaster_id,
                'source': source,
                'phase': 'FORGING',
                'started_at': now,
                'ends_at': now + self.duration,
                'raid': event,
                'messages': 0,
                'participants': [],
                'emotes': 0,
                'charge': 0,
                'recent_chat': [],
                'last_chat_received_at': None,
                'relic': None,
            }
            self.store.save_session(session)
            return True

        if not session or event.get('broadcaster_user_id') != broadcaster_id:
            return False
        if now >= session['ends_at']:
            self.finish(session, 'timer')
            return True

        session['messages'] += 1
        uid = event.get('chatter_user_id') or event.get('chatter_user_login') or 'viewer'
        if uid not in session['participants']:
            session['participants'].append(uid)
        fragments = (event.get('message') or {}).get('fragments') or []
        emote_count = sum(bool(fragment.get('emote')) or fragment.get('type') == 'emote' for fragment in fragments)
        session['emotes'] += emote_count
        session['charge'] = min(100, session['messages'] * 5 + len(session['participants']) * 3 + session['emotes'] * 2)
        message = event.get('message') or {}
        text = message.get('text') or ''.join(str(fragment.get('text') or '') for fragment in fragments)
        session.setdefault('recent_chat', []).append({
            'user': event.get('chatter_user_name') or event.get('chatter_user_login') or 'viewer',
            'text': text,
            'emotes': emote_count,
            'received_at': now,
        })
        session['recent_chat'] = session['recent_chat'][-7:]
        session['last_chat_received_at'] = now
        self.store.save_session(session)
        return True

    def finish(self, session, reason):
        seed = f"{session['id']}:{session['messages']}:{len(session['participants'])}:{session['emotes']}"
        session.update(
            phase='ARCHIVED',
            completed_at=self.clock(),
            completion_reason=reason,
            relic=relic(seed),
        )
        self.store.save_session(session)

    def tick(self, broadcaster_id):
        session = self.store.current_session(broadcaster_id)
        if session and self.clock() >= session['ends_at']:
            self.finish(session, 'timer')
            return True
        return False

    def snapshot_sessions(self, broadcaster_id):
        self.tick(broadcaster_id)
        sessions = self.store.sessions(broadcaster_id)
        return [
            {
                **{key: value for key, value in session.items() if key != 'participants'},
                'unique_chatters': len(session.get('participants') or []),
            }
            for session in sessions
        ]
