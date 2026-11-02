import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from aiohttp import web, ClientSession
from aiohttp.test_utils import TestServer, TestClient
from app.engine import Engine, relic
from app.server import create_app
from app.twitch import Twitch


def packet(kind, ident, **event):
    return {'metadata': {'message_type': 'notification', 'message_id': ident},
            'payload': {'subscription': {'type': kind, 'status': 'enabled'}, 'event': event}}


def raid(ident='raid1'):
    return packet('channel.raid', ident, from_broadcaster_user_name='Raider', viewers=12, to_broadcaster_user_id='42')


def chat(ident='chat1', user='u1'):
    return packet('channel.chat.message', ident, broadcaster_user_id='42', chatter_user_id=user,
                  chatter_user_name=user, message={'text': 'W raid 🔥',
                  'fragments': [{'type': 'text', 'text': 'W raid '}, {'type': 'emote', 'text': '🔥'}]})


class EngineTests(unittest.TestCase):
    def test_dedup_timer_archive_restart_and_seed(self):
        with tempfile.TemporaryDirectory() as folder:
            now = [1000]; path = folder+'/test.sqlite3'
            e = Engine(path, clock=lambda: now[0])
            e.apply(raid()); e.apply(chat()); e.apply(chat()); e.apply(chat('chat2')); e.apply(chat('chat3', 'u2'))
            s = e.current('twitch')
            self.assertEqual((s['messages'], len(s['participants']), s['emotes'], s['charge']), (3, 2, 3, 27))
            self.assertEqual(len(s['recent_chat']), 3)
            self.assertEqual((s['recent_chat'][-1]['user'], s['recent_chat'][-1]['text'], s['recent_chat'][-1]['emotes']), ('u2', 'W raid 🔥', 1))
            now[0] += 46; e.tick(); saved = e.sessions()[0]
            self.assertEqual(saved['phase'], 'ARCHIVED')
            self.assertEqual(saved['relic'], relic(saved['relic']['seed']))
            e.db.close(); restarted = Engine(path)
            self.assertEqual(restarted.sessions()[0], saved)
            self.assertFalse(restarted.apply(raid()))
            restarted.db.close()

    def test_sources_and_late_chat_are_isolated(self):
        now = [1]; e = Engine(':memory:', clock=lambda: now[0])
        e.apply(raid(), 'simulation'); e.apply(chat())
        self.assertEqual(e.current('simulation')['messages'], 0)
        now[0] = 50; e.apply(chat('late'), 'simulation')
        self.assertEqual(e.sessions()[0]['messages'], 0)
        self.assertEqual(e.sessions()[0]['phase'], 'ARCHIVED'); e.db.close()

    def test_second_raid_preserves_first(self):
        e = Engine(':memory:'); e.apply(raid()); e.apply(raid('raid2'))
        self.assertEqual(len(e.sessions()), 2)
        self.assertEqual(sum(s['phase']=='ARCHIVED' for s in e.sessions()), 1); e.db.close()

    def test_other_broadcaster_cannot_charge_existing_forge(self):
        e = Engine(':memory:'); e.apply(raid())
        wrong = chat('other-channel'); wrong['payload']['event']['broadcaster_user_id'] = 'other'
        e.apply(wrong)
        self.assertEqual(e.current('twitch')['messages'], 0)
        e.db.close()


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_sse_and_simulation_guards(self):
        with patch.dict(os.environ, {'RAIDRELIC_SIMULATION':'1'}, clear=True): app = create_app(':memory:')
        async with TestClient(TestServer(app)) as client:
            self.assertEqual((await client.get('/')).status, 200)
            async with client.get('/api/events') as r:
                initial = json.loads((await r.content.readline()).decode()[6:])
                self.assertEqual(initial['connection']['state'], 'credentials_required')
            self.assertEqual((await client.post('/dev/simulate', json={'kind':'raid'}, headers={'Origin':'https://evil.invalid'})).status, 403)
            await client.post('/dev/simulate', json={'kind':'raid'})
            state = await (await client.post('/dev/simulate', json={'kind':'chat'})).json()
            self.assertEqual(state['sessions'][0]['source'], 'simulation')
            self.assertEqual(state['sessions'][0]['messages'], 1)
            self.assertEqual((await client.get('/auth/callback?state=bad&code=bad')).status, 403)
            self.assertEqual((await client.get('/overlay/simulation')).status, 200)
        with patch.dict(os.environ, {}, clear=True): app = create_app(':memory:')
        async with TestClient(TestServer(app)) as client:
            self.assertEqual((await client.post('/dev/simulate', json={'kind':'raid'})).status, 404)

    async def test_eventsub_contract_reconnect_adapter(self):
        """Local fake Twitch transport. NOT live Twitch evidence."""
        subscriptions, seen = [], []
        async def validate(req):
            return web.json_response({'client_id':'client', 'user_id':'42','login':'receiver','scopes':['user:read:chat']})
        async def subscribe(req):
            self.assertEqual(req.headers['Authorization'], 'Bearer fake'); subscriptions.append(await req.json())
            return web.json_response({'data':[{'status':'enabled'}]},status=202)
        async def socket(req):
            ws=web.WebSocketResponse(); await ws.prepare(req)
            await ws.send_json({'metadata':{'message_type':'session_welcome'},'payload':{'session':{'id':req.path,'keepalive_timeout_seconds':10}}})
            if req.path == '/ws':
                while len(subscriptions)<2: await asyncio.sleep(.01)
                await ws.send_json(raid())
                await ws.send_json({'metadata':{'message_type':'session_reconnect'},'payload':{'session':{'reconnect_url':str(server.make_url('/next')).replace('http:','ws:')}}})
            else:
                await ws.send_json(chat()); await ws.send_json(chat())
                wrong=chat('wrong'); wrong['payload']['event']['broadcaster_user_id']='other'
                await ws.send_json(wrong); seen.append(True)
            async for _ in ws: pass
            return ws
        mock=web.Application(); mock.add_routes([web.get('/validate',validate),web.post('/subscriptions',subscribe),web.get('/ws',socket),web.get('/next',socket)])
        async with TestServer(mock) as server, ClientSession() as http:
            now=[1000]; e=Engine(':memory:',clock=lambda:now[0]); t=Twitch(e,'client','fake',http)
            t.validate_url=str(server.make_url('/validate')); t.api_url=str(server.make_url('/subscriptions'))
            t.ws_url=str(server.make_url('/ws')).replace('http:','ws:'); t.task=asyncio.create_task(t.run())
            try:
                async with asyncio.timeout(5):
                    while not seen or not e.current('twitch') or e.current('twitch')['messages'] != 1: await asyncio.sleep(.01)
                self.assertEqual(len(subscriptions),2)
                self.assertEqual(subscriptions[0]['condition'],{'to_broadcaster_user_id':'42'})
                self.assertEqual(subscriptions[1]['condition'],{'broadcaster_user_id':'42','user_id':'42'})
                self.assertEqual(t.status['state'],'connected'); now[0]+=46; e.tick()
                self.assertEqual(e.sessions()[0]['phase'],'ARCHIVED')
            finally: await t.stop(); e.db.close()


if __name__ == '__main__': unittest.main()
