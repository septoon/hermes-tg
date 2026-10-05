"""Reuse Hermes OIDC authentication and bind sessions to an allowed Telegram ID."""
from dataclasses import replace
import logging
import os

from hermes_cli.dashboard_auth import InvalidCodeError
from plugins.dashboard_auth._shared import SkipRegistration, register_provider
from plugins.dashboard_auth.self_hosted import SelfHostedOIDCProvider

logger = logging.getLogger(__name__)
LAST_SKIP_REASON = ""


class TelegramAuthProvider(SelfHostedOIDCProvider):
    name = "telegram"
    display_name = "Telegram"

    def __init__(self, *, client_id, client_secret, allowed_users):
        if not client_id.isdecimal() or not client_secret:
            raise ValueError("Telegram Login Client ID and Client Secret are required")
        users = frozenset(part.strip() for part in allowed_users.split(",") if part.strip())
        if not users or any(not user.isdecimal() for user in users):
            raise ValueError("TELEGRAM_ALLOWED_USERS must contain explicit numeric user IDs")
        self._allowed_users = users
        super().__init__(
            issuer="https://oauth.telegram.org", client_id=client_id,
            client_secret=client_secret, scopes="openid profile",
        )

    def _telegram_id(self, claims):
        value = claims.get("id")
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise InvalidCodeError("Telegram identity is missing")
        user_id = str(value)
        if user_id not in self._allowed_users:
            raise InvalidCodeError("This Telegram account is not allowed")
        return user_id

    def _verify_id_token(self, id_token):
        # Parent verifies Telegram's signature, issuer, audience and expiration first.
        claims = super()._verify_id_token(id_token)
        self._telegram_id(claims)
        return claims

    # The parent exposes this alias for verification on every authenticated request.
    _claims_for = _verify_id_token

    def _session(self, id_token, refresh_token, claims):
        return replace(
            super()._session(id_token, refresh_token, claims),
            user_id=self._telegram_id(claims),
        )


def _settings():
    names = (
        "HERMES_TELEGRAM_OIDC_CLIENT_ID", "HERMES_TELEGRAM_OIDC_CLIENT_SECRET",
        "TELEGRAM_ALLOWED_USERS",
    )
    values = [os.environ.get(name, "").strip() for name in names]
    if not all(values):
        raise SkipRegistration("Telegram Login credentials or owner allowlist are missing")
    return dict(zip(("client_id", "client_secret", "allowed_users"), values))


def register(ctx):
    global LAST_SKIP_REASON
    _, LAST_SKIP_REASON = register_provider(
        ctx, logger, "telegram-auth", TelegramAuthProvider, _settings,
    )
