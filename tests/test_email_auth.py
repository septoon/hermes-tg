"""OTP abuse boundaries and durable, revocable dashboard sessions."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'hermes-agent'))
from hermes_cli.dashboard_auth import InvalidCredentialsError, RefreshExpiredError

spec = importlib.util.spec_from_file_location('email_plugin', ROOT / 'plugins/telegram-auth/__init__.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class EmailAuthTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        env = patch.dict(os.environ, HERMES_HOME=self.home.name)
        env.start()
        self.addCleanup(env.stop)
        self.assertIsNotNone(getattr(module, 'EmailAuthProvider', None), 'Email login is missing')
        self.provider = module.EmailAuthProvider(email='owner@example.com', user_id='274685406')
        self.delivered = []

    def challenge(self, email='owner@example.com'):
        return self.provider.request_code(email, lambda address, code: self.delivered.append((address, code)))

    def login(self):
        challenge = self.challenge()
        return self.provider.complete_password_login(
            username='owner@example.com', password=f'{challenge}.{self.delivered[-1][1]}')

    def test_session_survives_restart_and_has_no_server_expiry(self):
        session = self.login()
        restarted = module.EmailAuthProvider(email='owner@example.com', user_id='274685406')
        with patch('time.time', return_value=time.time() + 10 * 365 * 86400):
            verified = restarted.verify_session(access_token=session.access_token)
        self.assertEqual(verified.user_id, '274685406')
        self.assertEqual(verified.email, 'owner@example.com')
        files = list(Path(self.home.name).glob('*.sqlite3'))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
        raw = files[0].read_bytes()
        self.assertNotIn(session.access_token.encode(), raw)
        self.assertNotIn(session.refresh_token.encode(), raw)
        self.assertNotIn(self.delivered[0][1].encode(), raw)

    def test_logout_revokes_access_and_refresh_after_restart(self):
        session = self.login()
        self.provider.revoke_session(refresh_token=session.refresh_token)
        restarted = module.EmailAuthProvider(email='owner@example.com', user_id='274685406')
        self.assertIsNone(restarted.verify_session(access_token=session.access_token))
        with self.assertRaises(RefreshExpiredError):
            restarted.refresh_session(refresh_token=session.refresh_token)

    def test_code_is_one_use_and_bound_to_email_and_challenge(self):
        challenge = self.challenge()
        password = f'{challenge}.{self.delivered[0][1]}'
        with self.assertRaises(InvalidCredentialsError):
            self.provider.complete_password_login(username='attacker@example.com', password=password)
        with self.assertRaises(InvalidCredentialsError):
            self.provider.complete_password_login(username='owner@example.com', password=f'wrong.{self.delivered[0][1]}')
        self.provider.complete_password_login(username='owner@example.com', password=password)
        with self.assertRaises(InvalidCredentialsError):
            self.provider.complete_password_login(username='owner@example.com', password=password)

    def test_code_expires_and_attempt_budget_cannot_be_restarted(self):
        challenge = self.challenge()
        good = f'{challenge}.{self.delivered[0][1]}'
        for _ in range(5):
            with self.assertRaises(InvalidCredentialsError):
                self.provider.complete_password_login(username='owner@example.com', password=f'{challenge}.bad')
        restarted = module.EmailAuthProvider(email='owner@example.com', user_id='274685406')
        with self.assertRaises(InvalidCredentialsError):
            restarted.complete_password_login(username='owner@example.com', password=good)
        with patch('time.time', return_value=time.time() + 61):
            challenge = self.challenge()
        with patch('time.time', return_value=time.time() + 700), self.assertRaises(InvalidCredentialsError):
            restarted.complete_password_login(username='owner@example.com', password=f'{challenge}.{self.delivered[-1][1]}')

    def test_delivery_is_allowlisted_and_throttled_across_restart(self):
        self.challenge('attacker@example.com')
        self.assertEqual(self.delivered, [])
        self.challenge()
        restarted = module.EmailAuthProvider(email='owner@example.com', user_id='274685406')
        with self.assertRaises(module.RateLimitError):
            restarted.request_code('owner@example.com', lambda *_: None)

    def test_refresh_rotates_tokens_and_changed_owner_revokes_access(self):
        session = self.login()
        rotated = self.provider.refresh_session(refresh_token=session.refresh_token)
        self.assertIsNone(self.provider.verify_session(access_token=session.access_token))
        self.assertIsNotNone(self.provider.verify_session(access_token=rotated.access_token))
        with self.assertRaises(RefreshExpiredError):
            self.provider.refresh_session(refresh_token=session.refresh_token)
        changed = module.EmailAuthProvider(email='different@example.com', user_id='274685406')
        self.assertIsNone(changed.verify_session(access_token=rotated.access_token))
        with self.assertRaises(RefreshExpiredError):
            changed.refresh_session(refresh_token=rotated.refresh_token)

    def test_native_cookie_flow_survives_reload_and_logout_revokes_it(self):
        from fastapi import FastAPI, Request
        from fastapi.testclient import TestClient
        from hermes_cli.dashboard_auth.registry import register_global_provider, unregister_global_provider
        from hermes_cli.dashboard_auth.routes import router, _reset_password_rate_limit
        from hermes_cli.dashboard_auth.middleware import gated_auth_middleware
        _reset_password_rate_limit()
        register_global_provider(self.provider)
        self.addCleanup(unregister_global_provider, 'email', self.provider)
        app = FastAPI()
        app.state.auth_required = True
        app.middleware('http')(gated_auth_middleware)
        app.include_router(router)

        @app.get('/api/private')
        async def private(request: Request):
            return {'user_id': request.state.session.user_id}

        client = TestClient(app, base_url='https://hermes.lumastack.ru')
        self.assertEqual(client.get('/api/private').status_code, 401)
        challenge = self.challenge()
        response = client.post('/auth/password-login', json={
            'provider': 'email', 'username': 'owner@example.com',
            'password': f'{challenge}.{self.delivered[0][1]}',
        })
        self.assertEqual(response.status_code, 200)
        cookies = response.headers.get_list('set-cookie')
        access_cookie = next(x for x in cookies if x.startswith('__Host-hermes_session_at='))
        self.assertIn('HttpOnly', access_cookie)
        self.assertIn('Secure', access_cookie)
        self.assertIn('SameSite=lax', access_cookie)
        self.assertEqual(client.get('/api/private').json()['user_id'], '274685406')
        with patch('time.time', return_value=time.time() + 120):
            self.assertEqual(client.get('/api/private').status_code, 200)
        client.post('/auth/logout', follow_redirects=False)
        self.assertEqual(client.get('/api/private').status_code, 401)
