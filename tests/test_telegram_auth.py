"""Exercise signature validation and the owner boundary with real signed ID tokens."""
import importlib.util
from pathlib import Path
import sys
import time
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hermes-agent"))
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from hermes_cli.dashboard_auth import ProviderError, assert_protocol_compliance

spec = importlib.util.spec_from_file_location("telegram_auth", ROOT / "plugins/telegram-auth/__init__.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TelegramAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.provider = module.TelegramAuthProvider(
            client_id="123456789", client_secret="test-only-client-secret", allowed_users="274685406",
        )
        self.provider._discovery = {
            "issuer": "https://oauth.telegram.org",
            "jwks_uri": "https://oauth.telegram.org/.well-known/jwks.json",
        }
        self.provider._discovery_fetched_at = time.time()
        self.provider._jwks_client = SimpleNamespace(
            get_signing_key_from_jwt=lambda _: SimpleNamespace(key=self.key.public_key()),
        )

    def token(self, **changes):
        claims = dict(
            iss="https://oauth.telegram.org", aud="123456789", sub="opaque-oidc-subject",
            id=274685406, name="Owner", iat=int(time.time()), exp=int(time.time()) + 300,
        )
        claims.update(changes)
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "test"})

    def test_owner_session_is_bound_to_telegram_id(self):
        assert_protocol_compliance(module.TelegramAuthProvider)
        session = self.provider.verify_session(access_token=self.token())
        self.assertEqual(session.user_id, "274685406")
        self.assertEqual(session.provider, "telegram")

    def test_foreign_missing_or_boolean_telegram_identity_is_rejected(self):
        for user_id in (123, None, True, "opaque-oidc-subject"):
            with self.subTest(user_id=user_id):
                self.assertIsNone(self.provider.verify_session(access_token=self.token(id=user_id)))

    def test_expired_wrong_issuer_and_wrong_audience_are_rejected(self):
        self.assertIsNone(self.provider.verify_session(access_token=self.token(exp=int(time.time()) - 60)))
        for changes in ({"iss": "https://attacker.example"}, {"aud": "other-client"}):
            with self.subTest(changes=changes), self.assertRaises(ProviderError):
                self.provider.verify_session(access_token=self.token(**changes))

    def test_forged_signature_is_rejected(self):
        attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        claims = jwt.decode(self.token(), options={"verify_signature": False})
        forged = jwt.encode(claims, attacker_key, algorithm="RS256")
        with self.assertRaises(ProviderError):
            self.provider.verify_session(access_token=forged)

    def test_invalid_allowlist_fails_closed(self):
        for allowlist in ("", "*", "274685406,anyone"):
            with self.subTest(allowlist=allowlist), self.assertRaises(ValueError):
                module.TelegramAuthProvider(client_id="123", client_secret="test", allowed_users=allowlist)


if __name__ == "__main__":
    unittest.main()
