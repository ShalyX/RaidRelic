import asyncio
import contextlib
import json
import os
from pathlib import Path
import secrets
import time
from urllib.parse import urlencode
import uuid

import aiohttp
from aiohttp import web
from app.engine import Engine
from app.twitch import Twitch

ROOT = Path(__file__).resolve().parent
ENGINE_KEY = web.AppKey('engine', Engine)
HTTP_KEY = web.AppKey('http', aiohttp.ClientSession)


def create_app(db_path=None):
    engine = Engine(db_path or os.getenv('RAIDRELIC_DB', 'raidrelic.sqlite3'))
    queues = set()
    client_id = os.getenv('TWITCH_CLIENT_ID', '')
    client_secret = os.getenv('TWITCH_CLIENT_SECRET', '')
    public_mode = os.getenv('RAIDRELIC_PUBLIC') == '1'
    base_url = os.getenv('RAIDRELIC_BASE_URL', 'http://localhost:3000').rstrip('/')
    redirect = os.getenv('TWITCH_REDIRECT_URI') or base_url + '/auth/callback'
    simulation = os.getenv('RAIDRELIC_SIMULATION') == '1'
    csrf = {}
    twitch = None

    def changed():
        for q in queues:
            if q.empty():
                q.put_nowait(True)
    engine.changed = changed

    @web.middleware
    async def local_only(req, handler):
        # Local by default. A dedicated hosted instance can opt into public mode.
        if not public_mode and req.host.split(':')[0] not in ('localhost', '127.0.0.1'):
            raise web.HTTPForbidden(text='Use localhost or 127.0.0.1.')
        origin = req.headers.get('Origin')
        proto = req.headers.get('X-Forwarded-Proto', req.scheme)
        if origin and origin != f'{proto}://{req.host}':
            raise web.HTTPForbidden(text='Same-origin requests only.')
        response = await handler(req)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    app = web.Application(middlewares=[local_only])
    app[ENGINE_KEY] = engine

    def snapshot():
        status = twitch.status if twitch else {'state': 'credentials_required', 'channel_id': None, 'subscriptions': []}
        sessions = engine.sessions()
        return {'connection': status, 'simulation_enabled': simulation, 'service_ready': bool(client_id and client_secret), 'now': time.time(),
                'sessions': [{**{k:v for k,v in s.items() if k != 'participants'},
                              'unique_chatters': len(s['participants'])} for s in sessions]}

    async def state(req):
        return web.json_response(snapshot())

    async def page(req):
        return web.FileResponse(ROOT / 'index.html')

    async def stream(req):
        response = web.StreamResponse(headers={'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store'})
        await response.prepare(req)
        q = asyncio.Queue(maxsize=1)
        queues.add(q)
        try:
            while True:
                await response.write(('data: ' + json.dumps(snapshot()) + '\n\n').encode())
                try:
                    await asyncio.wait_for(q.get(), 1)
                except asyncio.TimeoutError:
                    pass
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            queues.discard(q)
        return response

    async def connect(token, refresh_token=''):
        nonlocal twitch
        if twitch:
            await twitch.stop()
        twitch = Twitch(engine, client_id, token, app[HTTP_KEY], client_secret=client_secret, refresh_token=refresh_token)
        twitch.task = asyncio.create_task(twitch.run())

    async def auth(req):
        if not client_id or not client_secret:
            raise web.HTTPServiceUnavailable(text='Configure TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET in the runtime, then restart. Never paste credentials in chat.')
        nonce = secrets.token_urlsafe(32)
        csrf.clear()
        csrf[nonce] = time.monotonic() + 600
        response = web.HTTPFound('https://id.twitch.tv/oauth2/authorize?' + urlencode({
            'response_type': 'code', 'client_id': client_id, 'redirect_uri': redirect,
            'scope': 'user:read:chat', 'state': nonce}))
        response.set_cookie('raidrelic_oauth', nonce, httponly=True, samesite='Lax', max_age=600)
        return response

    async def callback(req):
        nonce = req.query.get('state', '')
        if not nonce or not secrets.compare_digest(nonce, req.cookies.get('raidrelic_oauth', '')) or csrf.pop(nonce, 0) < time.monotonic():
            raise web.HTTPForbidden(text='OAuth state invalid or expired; reconnect.')
        if not req.query.get('code'):
            raise web.HTTPBadRequest(text='Twitch authorization was not granted.')
        async with app[HTTP_KEY].post('https://id.twitch.tv/oauth2/token', data={
            'client_id': client_id, 'client_secret': client_secret, 'code': req.query['code'],
            'grant_type': 'authorization_code', 'redirect_uri': redirect}) as r:
            if r.status != 200:
                raise web.HTTPBadGateway(text='Token exchange failed; reconnect Twitch.')
            token_data = await r.json()
            token = token_data['access_token']
            refresh_token = token_data.get('refresh_token', '')
        await connect(token, refresh_token)
        response = web.HTTPFound('/')
        response.del_cookie('raidrelic_oauth')
        return response

    async def simulate(req):
        if not simulation:
            raise web.HTTPNotFound()
        data = await req.json()
        kind = data.get('kind')
        if kind == 'raid':
            typ, event = 'channel.raid', {'from_broadcaster_user_name': 'SIMULATED Raider',
                'from_broadcaster_user_id': 'sim-raider', 'to_broadcaster_user_id': 'simulation', 'viewers': 12}
        elif kind == 'chat':
            user = str(data.get('user', 'sim-viewer'))[:50]
            text = str(data.get('text', 'W raid 🔥'))[:280]
            typ, event = 'channel.chat.message', {'broadcaster_user_id': 'simulation',
                'chatter_user_id': user, 'chatter_user_name': user,
                'message': {'text': text, 'fragments': [{'type': 'text', 'text': text}, {'type': 'emote', 'text': '🔥'}]}}
        else:
            raise web.HTTPBadRequest(text='kind must be raid or chat')
        engine.apply({'metadata': {'message_id': str(uuid.uuid4())},
                      'payload': {'subscription': {'type': typ}, 'event': event}}, 'simulation')
        return web.json_response(snapshot())

    async def lifecycle(app):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15), trust_env=True) as http:
            app[HTTP_KEY] = http
            if os.getenv('TWITCH_ACCESS_TOKEN') and client_id:
                await connect(os.environ['TWITCH_ACCESS_TOKEN'], os.getenv('TWITCH_REFRESH_TOKEN', ''))
            async def ticker():
                while True:
                    engine.tick()
                    await asyncio.sleep(.2)
            task = asyncio.create_task(ticker())
            yield
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            if twitch:
                await twitch.stop()
            engine.db.close()

    app.cleanup_ctx.append(lifecycle)
    app.add_routes([web.get('/', page), web.get('/overlay/{channel}', page),
                    web.get('/api/state', state), web.get('/api/events', stream),
                    web.get('/auth/twitch', auth), web.get('/auth/callback', callback),
                    web.post('/dev/simulate', simulate)])
    return app


if __name__ == '__main__':
    host = '0.0.0.0' if os.getenv('RAIDRELIC_PUBLIC') == '1' else '127.0.0.1'
    web.run_app(create_app(), host=host, port=int(os.getenv('PORT', '3000')), access_log=None)
