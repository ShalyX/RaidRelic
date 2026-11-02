import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse

from app.hosted_engine import HostedEngine
from app.hosted_store import HostedStore, TokenVault, storage_is_durable


TWITCH_AUTHORIZE = 'https://id.twitch.tv/oauth2/authorize'
TWITCH_TOKEN = 'https://id.twitch.tv/oauth2/token'
TWITCH_VALIDATE = 'https://id.twitch.tv/oauth2/validate'
TWITCH_USERS = 'https://api.twitch.tv/helix/users'
TWITCH_EVENTSUB = 'https://api.twitch.tv/helix/eventsub/subscriptions'
REQUIRED_SCOPES = {'user:read:chat', 'user:bot', 'channel:bot'}

app = FastAPI(title='RaidRelic Hosted', docs_url=None, redoc_url=None)
store = HostedStore()
vault = TokenVault()
forge = HostedEngine(store)


def client_id():
    return os.getenv('TWITCH_CLIENT_ID', '').strip()


def client_secret():
    return os.getenv('TWITCH_CLIENT_SECRET', '').strip()


def session_secret():
    return os.getenv('RAIDRELIC_SESSION_SECRET', '').encode()


def webhook_secret():
    return os.getenv('RAIDRELIC_WEBHOOK_SECRET', '').encode()


def maintenance_secret():
    return os.getenv('RAIDRELIC_MAINTENANCE_SECRET', '').strip()


def public_base(request: Request):
    configured = os.getenv('RAIDRELIC_BASE_URL', '').strip().rstrip('/')
    if configured:
        return configured
    vercel_url = os.getenv('VERCEL_URL', '').strip()
    if vercel_url:
        return 'https://' + vercel_url.rstrip('/')
    return str(request.base_url).rstrip('/')


def service_ready():
    durable_ok = storage_is_durable() or not os.getenv('VERCEL')
    return bool(client_id() and client_secret() and session_secret() and webhook_secret() and vault.ready and durable_ok)


def sign_session(twitch_user_id):
    secret = session_secret()
    if not secret:
        return ''
    signature = hmac.new(secret, twitch_user_id.encode(), hashlib.sha256).hexdigest()
    return twitch_user_id + '.' + signature


def verify_session(value):
    if not value or '.' not in value or not session_secret():
        return None
    twitch_user_id, supplied = value.rsplit('.', 1)
    expected = hmac.new(session_secret(), twitch_user_id.encode(), hashlib.sha256).hexdigest()
    return twitch_user_id if hmac.compare_digest(supplied, expected) else None


def connection_payload(streamer, oauth_status='valid'):
    if not streamer:
        return {'state': 'credentials_required', 'channel_id': None, 'login': None, 'overlay_key': None, 'subscriptions': []}
    subscriptions = streamer.subscriptions or []
    complete = {'channel.raid', 'channel.chat.message'}.issubset(set(subscriptions))
    revoked = oauth_status == 'revoked'
    return {
        'state': 'authorization_required' if revoked or not complete else 'connected',
        'channel_id': streamer.twitch_user_id,
        'login': streamer.login,
        'overlay_key': streamer.overlay_key,
        'subscriptions': subscriptions,
        'oauth_status': oauth_status,
        'error': 'Twitch authorization was revoked or expired. Reconnect Twitch.' if revoked else (
            None if complete else 'EventSub setup incomplete. Reconnect Twitch to repair subscriptions.'),
    }


def oauth_redirect_uri(request):
    return public_base(request) + '/auth/callback'


async def twitch_app_token(http):
    response = await http.post(TWITCH_TOKEN, data={
        'client_id': client_id(),
        'client_secret': client_secret(),
        'grant_type': 'client_credentials',
    })
    if response.status_code != 200:
        raise RuntimeError('Twitch rejected RaidRelic app credentials.')
    return response.json()['access_token']


async def existing_subscriptions(http, app_token, kind):
    response = await http.get(TWITCH_EVENTSUB, params={'type': kind}, headers={
        'Client-Id': client_id(),
        'Authorization': 'Bearer ' + app_token,
    })
    if response.status_code != 200:
        raise RuntimeError(f'Twitch could not list {kind} subscriptions (HTTP {response.status_code}).')
    return response.json().get('data', [])


async def ensure_subscription(http, app_token, broadcaster_id, kind, callback):
    condition = {'to_broadcaster_user_id': broadcaster_id} if kind == 'channel.raid' else {
        'broadcaster_user_id': broadcaster_id,
        'user_id': broadcaster_id,
    }
    matches = []
    for item in await existing_subscriptions(http, app_token, kind):
        if item.get('condition') == condition:
            matches.append(item)

    for item in matches:
        transport = item.get('transport') or {}
        if transport.get('method') == 'webhook' and transport.get('callback') == callback and item.get('status') in ('enabled', 'webhook_callback_verification_pending'):
            return True

    for item in matches:
        response = await http.delete(TWITCH_EVENTSUB, params={'id': item['id']}, headers={
            'Client-Id': client_id(),
            'Authorization': 'Bearer ' + app_token,
        })
        if response.status_code not in (204, 404):
            raise RuntimeError(f'Twitch could not replace stale {kind} subscription.')

    response = await http.post(TWITCH_EVENTSUB, headers={
        'Client-Id': client_id(),
        'Authorization': 'Bearer ' + app_token,
        'Content-Type': 'application/json',
    }, json={
        'type': kind,
        'version': '1',
        'condition': condition,
        'transport': {
            'method': 'webhook',
            'callback': callback,
            'secret': webhook_secret().decode(),
        },
    })
    if response.status_code != 202:
        detail = response.text[:280].replace('\n', ' ')
        raise RuntimeError(f'Twitch rejected {kind} EventSub setup (HTTP {response.status_code}: {detail}).')
    return True


async def ensure_subscriptions(request, broadcaster_id):
    callback = public_base(request) + '/eventsub/twitch'
    async with httpx.AsyncClient(timeout=15) as http:
        app_token = await twitch_app_token(http)
        active = []
        for kind in ('channel.raid', 'channel.chat.message'):
            if await ensure_subscription(http, app_token, broadcaster_id, kind, callback):
                active.append(kind)
        return active


async def maintain_user_authorization(streamer):
    if not streamer:
        return 'missing'
    current_status = store.oauth_status(streamer.twitch_user_id)
    if not store.claim_oauth_check(streamer.twitch_user_id):
        return 'valid' if current_status in ('valid', 'checking') else current_status

    retry_at = time.time() + 60
    try:
        access_token = vault.decrypt(streamer.access_token_enc)
        refresh_token = vault.decrypt(streamer.refresh_token_enc)
        async with httpx.AsyncClient(timeout=15) as http:
            validate = await http.get(TWITCH_VALIDATE, headers={'Authorization': 'OAuth ' + access_token})
            if validate.status_code == 200:
                data = validate.json()
                scopes = set(data.get('scopes') or [])
                identity_ok = data.get('user_id') == streamer.twitch_user_id and data.get('client_id') == client_id()
                if identity_ok and REQUIRED_SCOPES.issubset(scopes):
                    store.set_oauth_health(streamer.twitch_user_id, 'valid')
                    return 'valid'
                store.set_oauth_health(streamer.twitch_user_id, 'revoked', next_check_at=time.time() + 3600)
                return 'revoked'

            if validate.status_code == 401 and refresh_token:
                refreshed = await http.post(TWITCH_TOKEN, data={
                    'client_id': client_id(),
                    'client_secret': client_secret(),
                    'grant_type': 'refresh_token',
                    'refresh_token': refresh_token,
                })
                if refreshed.status_code == 200:
                    token_data = refreshed.json()
                    new_access = token_data.get('access_token', '')
                    new_refresh = token_data.get('refresh_token') or refresh_token
                    verify = await http.get(TWITCH_VALIDATE, headers={'Authorization': 'OAuth ' + new_access})
                    if verify.status_code == 200:
                        data = verify.json()
                        scopes = set(data.get('scopes') or [])
                        identity_ok = data.get('user_id') == streamer.twitch_user_id and data.get('client_id') == client_id()
                        if identity_ok and REQUIRED_SCOPES.issubset(scopes):
                            store.update_tokens(
                                streamer.twitch_user_id,
                                vault.encrypt(new_access),
                                vault.encrypt(new_refresh),
                            )
                            store.set_oauth_health(streamer.twitch_user_id, 'valid')
                            return 'valid'
                    store.set_oauth_health(streamer.twitch_user_id, 'revoked', next_check_at=time.time() + 3600)
                    return 'revoked'
                if refreshed.status_code in (400, 401):
                    store.set_oauth_health(streamer.twitch_user_id, 'revoked', next_check_at=time.time() + 3600)
                    return 'revoked'

            if validate.status_code == 401:
                store.set_oauth_health(streamer.twitch_user_id, 'revoked', next_check_at=time.time() + 3600)
                return 'revoked'
    except (httpx.RequestError, ValueError, RuntimeError):
        pass

    store.set_oauth_health(streamer.twitch_user_id, 'unknown', next_check_at=retry_at)
    return 'valid' if current_status in ('valid', 'checking') else current_status


@app.get('/health')
async def health():
    return {
        'ok': True,
        'service_ready': service_ready(),
        'durable_storage': storage_is_durable(),
        'oauth': bool(client_id() and client_secret()),
        'token_encryption': vault.ready,
        'webhook_verification': bool(webhook_secret()),
    }


@app.post('/internal/oauth-maintenance')
async def oauth_maintenance(request: Request):
    configured = maintenance_secret()
    supplied = request.headers.get('Authorization', '')
    expected = 'Bearer ' + configured if configured else ''
    if not expected or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail='Unauthorized.')

    counts = {'valid': 0, 'revoked': 0, 'unknown': 0, 'missing': 0}
    streamers = store.list_streamers()
    for streamer in streamers:
        status = await maintain_user_authorization(streamer)
        counts[status] = counts.get(status, 0) + 1
    return {'ok': True, 'streamers': len(streamers), 'status': counts}


@app.get('/api/state')
async def state(request: Request, overlay: str | None = None):
    streamer = store.get_streamer_by_overlay(overlay) if overlay else None
    oauth_status = 'valid'
    if not streamer:
        twitch_user_id = verify_session(request.cookies.get('raidrelic_session'))
        streamer = store.get_streamer_by_id(twitch_user_id) if twitch_user_id else None
        if streamer:
            oauth_status = await maintain_user_authorization(streamer)
    elif streamer:
        oauth_status = store.oauth_status(streamer.twitch_user_id)
    sessions = forge.snapshot_sessions(streamer.twitch_user_id) if streamer else []
    return {
        'connection': connection_payload(streamer, oauth_status),
        'simulation_enabled': False,
        'service_ready': service_ready(),
        'now': time.time(),
        'sessions': sessions,
    }


@app.get('/auth/twitch')
async def auth_twitch(request: Request):
    if not service_ready():
        raise HTTPException(status_code=503, detail='RaidRelic hosted service is not fully configured yet.')
    state = store.create_oauth_state(ttl=600)
    url = TWITCH_AUTHORIZE + '?' + urlencode({
        'response_type': 'code',
        'client_id': client_id(),
        'redirect_uri': oauth_redirect_uri(request),
        'scope': ' '.join(sorted(REQUIRED_SCOPES)),
        'state': state,
        'force_verify': 'false',
    })
    response = RedirectResponse(url, status_code=302)
    response.set_cookie('raidrelic_oauth', state, httponly=True, secure=public_base(request).startswith('https://'), samesite='lax', max_age=600)
    return response


@app.get('/auth/callback')
async def auth_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    expected_state = request.cookies.get('raidrelic_oauth')
    cookie_mismatch = bool(expected_state and state and not secrets.compare_digest(state, expected_state))
    state_valid = bool(state and not cookie_mismatch and store.consume_oauth_state(state))
    if not state_valid:
        session_user_id = verify_session(request.cookies.get('raidrelic_session'))
        if session_user_id and store.get_streamer_by_id(session_user_id):
            return RedirectResponse('/', status_code=303)
        raise HTTPException(status_code=403, detail='OAuth state invalid or expired. Reconnect Twitch.')
    if error or not code:
        raise HTTPException(status_code=400, detail='Twitch authorization was not granted.')

    async with httpx.AsyncClient(timeout=15) as http:
        token_response = await http.post(TWITCH_TOKEN, data={
            'client_id': client_id(),
            'client_secret': client_secret(),
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': oauth_redirect_uri(request),
        })
        if token_response.status_code != 200:
            raise HTTPException(status_code=502, detail='Twitch token exchange failed. Reconnect Twitch.')
        token_data = token_response.json()
        access_token = token_data['access_token']
        refresh_token = token_data.get('refresh_token', '')

        validate_response = await http.get(TWITCH_VALIDATE, headers={'Authorization': 'OAuth ' + access_token})
        if validate_response.status_code != 200:
            raise HTTPException(status_code=502, detail='Twitch token validation failed.')
        validated = validate_response.json()
        scopes = set(validated.get('scopes') or [])
        if not REQUIRED_SCOPES.issubset(scopes):
            raise HTTPException(status_code=403, detail='RaidRelic did not receive all required Twitch permissions. Reconnect and approve the requested scopes.')
        twitch_user_id = validated.get('user_id')
        login = validated.get('login') or 'streamer'
        if not twitch_user_id:
            raise HTTPException(status_code=502, detail='Twitch did not return a broadcaster identity.')

        display_name = login
        users_response = await http.get(TWITCH_USERS, headers={
            'Client-Id': client_id(),
            'Authorization': 'Bearer ' + access_token,
        })
        if users_response.status_code == 200 and users_response.json().get('data'):
            display_name = users_response.json()['data'][0].get('display_name') or login

    streamer = store.upsert_streamer(
        twitch_user_id=twitch_user_id,
        login=login,
        display_name=display_name,
        access_token_enc=vault.encrypt(access_token),
        refresh_token_enc=vault.encrypt(refresh_token),
    )
    store.set_oauth_health(twitch_user_id, 'valid')

    try:
        subscriptions = await ensure_subscriptions(request, twitch_user_id)
        store.set_subscriptions(twitch_user_id, subscriptions)
    except Exception:
        store.set_subscriptions(twitch_user_id, [])

    response = RedirectResponse('/', status_code=302)
    response.set_cookie(
        'raidrelic_session', sign_session(streamer.twitch_user_id),
        httponly=True, secure=public_base(request).startswith('https://'), samesite='lax', max_age=60 * 60 * 24 * 30)
    response.delete_cookie('raidrelic_oauth')
    return response


def verify_eventsub_signature(request: Request, body: bytes):
    secret = webhook_secret()
    if not secret:
        return False
    message_id = request.headers.get('Twitch-Eventsub-Message-Id', '')
    timestamp = request.headers.get('Twitch-Eventsub-Message-Timestamp', '')
    supplied = request.headers.get('Twitch-Eventsub-Message-Signature', '')
    if not message_id or not timestamp or not supplied.startswith('sha256='):
        return False
    try:
        parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        age = abs((datetime.now(timezone.utc) - parsed).total_seconds())
        if age > 600:
            return False
    except ValueError:
        return False
    digest = hmac.new(secret, message_id.encode() + timestamp.encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied, 'sha256=' + digest)


@app.post('/eventsub/twitch')
async def eventsub_twitch(request: Request):
    body = await request.body()
    if not verify_eventsub_signature(request, body):
        raise HTTPException(status_code=403, detail='Invalid EventSub signature.')
    try:
        packet = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail='Invalid EventSub payload.')

    message_type = request.headers.get('Twitch-Eventsub-Message-Type', '')
    if message_type == 'webhook_callback_verification':
        return PlainTextResponse(packet.get('challenge', ''))
    if message_type == 'notification':
        metadata = {
            'message_id': request.headers.get('Twitch-Eventsub-Message-Id', ''),
            'message_timestamp': request.headers.get('Twitch-Eventsub-Message-Timestamp', ''),
            'message_type': message_type,
        }
        forge.apply({'metadata': metadata, 'payload': packet})
        return PlainTextResponse('', status_code=204)
    if message_type == 'revocation':
        broadcaster_id = HostedEngine.broadcaster_id(packet)
        streamer = store.get_streamer_by_id(broadcaster_id) if broadcaster_id else None
        if streamer:
            subscription = packet.get('subscription') or {}
            revoked_kind = subscription.get('type')
            store.set_subscriptions(broadcaster_id, [kind for kind in streamer.subscriptions if kind != revoked_kind])
            if subscription.get('status') in ('authorization_revoked', 'user_removed'):
                store.set_oauth_health(broadcaster_id, 'revoked', next_check_at=time.time() + 3600)
        return PlainTextResponse('', status_code=204)
    return PlainTextResponse('', status_code=204)
