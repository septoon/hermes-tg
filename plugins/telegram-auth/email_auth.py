"""Email OTP provider using the native Hermes cookie, logout and WebSocket framework."""
import secrets

from hermes_cli.dashboard_auth import DashboardAuthProvider, InvalidCredentialsError, RefreshExpiredError
from plugins.dashboard_auth._shared import NonInteractiveMixin

if __package__:
    from .sessions import SessionStore, RateLimitError
else:
    from sessions import SessionStore, RateLimitError


class EmailAuthProvider(NonInteractiveMixin, DashboardAuthProvider):
    name = 'email'
    display_name = 'Почта'
    supports_password = True  # The native credential endpoint receives challenge + OTP.
    _NOT_INTERACTIVE = 'Use the email code form.'

    def __init__(self, *, email, user_id):
        self.email = email.strip().lower()
        if '@' not in self.email or not user_id.isdecimal():
            raise ValueError('A login email and one verified Telegram owner ID are required')
        self.user_id = user_id
        self.store = SessionStore(self.name)

    def request_code(self, email, send):
        if email.strip().lower() != self.email:
            return secrets.token_urlsafe(32)
        challenge, code = self.store.issue_code(self.email)
        try:
            send(self.email, code)
        except Exception:
            self.store.cancel_code(challenge)
            raise
        return challenge

    def complete_password_login(self, *, username, password):
        email = username.strip().lower()
        challenge, sep, code = password.partition('.')
        if email != self.email or not sep or not self.store.consume_code(email, challenge, code):
            raise InvalidCredentialsError('Invalid or expired email code')
        return self.store.mint(user_id=self.user_id, email=email, display_name=email)

    def _allowed(self, session):
        return session is not None and session.user_id == self.user_id and session.email == self.email

    def verify_session(self, *, access_token):
        session = self.store.lookup(access_token)
        return session if self._allowed(session) else None

    def refresh_session(self, *, refresh_token):
        if not self._allowed(self.store.lookup(refresh_token, refresh=True)):
            raise RefreshExpiredError('This account is not allowed')
        return self.store.rotate(refresh_token)

    def revoke_session(self, *, refresh_token):
        self.store.revoke(refresh_token)
