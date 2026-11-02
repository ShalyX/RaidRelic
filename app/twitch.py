"""Real EventSub adapter; mock fixtures never enter this transport."""
import asyncio
import json
import time
import aiohttp

WS_URL = 'wss://eventsub.wss.twitch.tv/ws'
API_URL = 'https://api.twitch.tv/helix/eventsub/subscriptions'
VALIDATE_URL = 'https://id.twitch.tv/oauth2/validate'


class Twitch:
    def __init__(self, engine, client_id, token, http):
        self.engine, self.client_id, self.token, self.http = engine, client_id, token, http
        self.status = {'state': 'disconnected', 'channel_id': None, 'login': None, 'subscriptions': []}
        self.validated_at = 0
        self.task = None
        self.ws = None
        self.ws_url, self.api_url, self.validate_url = WS_URL, API_URL, VALIDATE_URL

    def update(self, **fields):
        self.status.update(fields)
        self.engine.changed()

    async def validate(self):
        async with self.http.get(self.validate_url, headers={'Authorization': 'OAuth ' + self.token}) as r:
            if r.status != 200:
                raise PermissionError('Twitch token invalid; reconnect Twitch.')
            data = await r.json()
        if data.get('client_id') != self.client_id or not data.get('user_id') or 'user:read:chat' not in data.get('scopes', []):
            raise PermissionError('Use broadcaster user token for this client with user:read:chat.')
        self.validated_at = time.monotonic()
        self.update(channel_id=data['user_id'], login=data['login'])

    async def subscribe(self, session_id):
        uid = self.status['channel_id']
        conditions = [('channel.raid', {'to_broadcaster_user_id': uid}),
                      ('channel.chat.message', {'broadcaster_user_id': uid, 'user_id': uid})]
        self.update(subscriptions=[])
        for kind, condition in conditions:
            async with self.http.post(self.api_url,
                headers={'Client-Id': self.client_id, 'Authorization': 'Bearer ' + self.token},
                json={'type': kind, 'version': '1', 'condition': condition,
                      'transport': {'method': 'websocket', 'session_id': session_id}}) as r:
                if r.status == 401:
                    raise PermissionError('Twitch authorization expired; reconnect Twitch.')
                if r.status != 202:
                    raise RuntimeError(f'Subscription {kind} rejected (HTTP {r.status}).')
                result = await r.json()
                if result['data'][0]['status'] != 'enabled':
                    raise RuntimeError('Twitch subscription is not enabled.')
                self.update(subscriptions=self.status['subscriptions'] + [kind])

    async def run_session(self, url, previous=None):
        ws = await self.http.ws_connect(url, autoping=True, timeout=aiohttp.ClientWSTimeout(ws_close=5))
        self.ws = ws
        timeout = 15
        welcomed = False
        try:
            while True:
                if time.monotonic() - self.validated_at >= 3600:
                    await self.validate()
                msg = await asyncio.wait_for(ws.receive(), timeout=timeout)
                if msg.type != aiohttp.WSMsgType.TEXT:
                    if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        raise ConnectionError('EventSub connection closed; missed events cannot be replayed.')
                    continue
                packet = json.loads(msg.data)
                kind = packet['metadata']['message_type']
                if kind == 'session_welcome':
                    session = packet['payload']['session']
                    timeout = (session.get('keepalive_timeout_seconds') or 10) + 5
                    if previous:
                        await previous.close()
                        previous = None
                    else:
                        await self.subscribe(session['id'])
                    welcomed = True
                    self.update(state='connected', error=None)
                elif kind == 'session_reconnect':
                    return packet['payload']['session']['reconnect_url'], ws
                elif kind == 'revocation':
                    self.update(subscriptions=[])
                    raise PermissionError('Twitch subscription revoked; reconnect Twitch.')
                elif kind == 'notification' and welcomed:
                    uid = self.status['channel_id']
                    p = packet['payload']
                    sub, event = p['subscription'], p['event']
                    typ = sub['type']
                    valid = ((typ == 'channel.raid' and event.get('to_broadcaster_user_id') == uid) or
                             (typ == 'channel.chat.message' and event.get('broadcaster_user_id') == uid))
                    if valid and sub.get('status') == 'enabled':
                        applied = self.engine.apply(packet, 'twitch')
                        if applied:
                            self.update(last_event={'id': packet['metadata']['message_id'], 'type': typ,
                                                   'received_at': time.time(),
                                                   'twitch_timestamp': packet['metadata'].get('message_timestamp')})
        except BaseException:
            await ws.close()
            if previous:
                await previous.close()
            raise
        finally:
            # Reconnect hands the still-open old socket to the successor.
            if ws.closed:
                self.ws = None

    async def run(self):
        backoff = 1
        while True:
            previous = None
            try:
                await self.validate()
                url = self.ws_url
                self.update(state='connecting', error=None)
                while True:
                    url, previous = await self.run_session(url, previous)
                    backoff = 1
            except asyncio.CancelledError:
                if previous:
                    await previous.close()
                if self.ws:
                    await self.ws.close()
                raise
            except PermissionError as exc:
                if previous:
                    await previous.close()
                self.token = ''
                self.update(state='authorization_required', error=str(exc), subscriptions=[])
                return
            except Exception as exc:
                if previous:
                    await previous.close()
                # Do not log HTTP request objects, headers, tokens, or raw URLs.
                self.update(state='retrying', error=type(exc).__name__ + ': connection/subscription unavailable', subscriptions=[])
                await asyncio.sleep(backoff)
                backoff = min(30, backoff * 2)

    async def stop(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.token = ''
