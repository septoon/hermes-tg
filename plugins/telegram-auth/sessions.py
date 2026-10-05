"""Private, shared SQLite storage. Credentials are stored only as SHA-256 hashes."""
from contextlib import contextmanager
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
import time

from hermes_cli.dashboard_auth import ProviderError, RefreshExpiredError, Session
from hermes_constants import get_hermes_home


class RateLimitError(Exception):
    pass


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class SessionStore:
    # Browser cookie retention is finite; the server session has no automatic expiry.
    COOKIE_EXPIRY = 253402300799  # 9999-12-31 UTC

    def __init__(self, provider):
        self.provider = provider
        self.path = get_hermes_home() / 'dashboard-sessions.sqlite3'

    @contextmanager
    def db(self):
        conn = None
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(fd)
            self.path.chmod(0o600)
            conn = sqlite3.connect(self.path, timeout=5)
            conn.row_factory = sqlite3.Row
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS sessions (
                    access_hash TEXT PRIMARY KEY, refresh_hash TEXT UNIQUE NOT NULL,
                    provider TEXT NOT NULL, user_id TEXT NOT NULL,
                    email TEXT NOT NULL, display_name TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS login_codes (
                    challenge_hash TEXT PRIMARY KEY, email TEXT NOT NULL,
                    code_hash TEXT NOT NULL, expires_at INTEGER NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS login_requests (
                    email TEXT NOT NULL, created_at INTEGER NOT NULL);
            ''')
            with conn:
                yield conn
        except (sqlite3.Error, OSError) as exc:
            raise ProviderError('Dashboard session storage unavailable') from exc
        finally:
            if conn is not None:
                conn.close()

    def session(self, row, access_token, refresh_token=''):
        return Session(
            user_id=row['user_id'], email=row['email'], display_name=row['display_name'],
            org_id='', provider=self.provider, expires_at=self.COOKIE_EXPIRY,
            access_token=access_token, refresh_token=refresh_token,
        )

    def mint(self, *, user_id, email='', display_name=''):
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        row = dict(user_id=user_id, email=email, display_name=display_name)
        with self.db() as db:
            db.execute('INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)',
                       (digest(access), digest(refresh), self.provider, user_id, email, display_name))
        return self.session(row, access, refresh)

    def lookup(self, token, *, refresh=False):
        if not token or len(token) != 43:
            return None
        column = 'refresh_hash' if refresh else 'access_hash'
        with self.db() as db:
            row = db.execute(f'SELECT * FROM sessions WHERE {column}=? AND provider=?',
                             (digest(token), self.provider)).fetchone()
        return self.session(row, '' if refresh else token) if row else None

    def rotate(self, refresh_token):
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM sessions WHERE refresh_hash=? AND provider=?',
                             (digest(refresh_token), self.provider)).fetchone()
            if row:
                db.execute('UPDATE sessions SET access_hash=?, refresh_hash=? WHERE refresh_hash=? AND provider=?',
                           (digest(access), digest(refresh), digest(refresh_token), self.provider))
        if row is None:
            raise RefreshExpiredError('Session was revoked or rotated')
        return self.session(row, access, refresh)

    def revoke(self, refresh_token):
        with self.db() as db:
            db.execute('DELETE FROM sessions WHERE refresh_hash=? AND provider=?',
                       (digest(refresh_token), self.provider))

    def issue_code(self, email):
        now = int(time.time())
        challenge, code = secrets.token_urlsafe(32), f'{secrets.randbelow(100000000):08d}'
        limited = False
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM login_requests WHERE created_at<?', (now - 3600,))
            db.execute('DELETE FROM login_codes WHERE expires_at<?', (now,))
            recent = db.execute('SELECT COUNT(*), MAX(created_at) FROM login_requests WHERE email=?', (email,)).fetchone()
            limited = recent[0] >= 5 or (recent[1] is not None and now - recent[1] < 60)
            if not limited:
                db.execute('INSERT INTO login_requests VALUES (?, ?)', (email, now))
                db.execute('INSERT INTO login_codes (challenge_hash, email, code_hash, expires_at) VALUES (?, ?, ?, ?)',
                           (digest(challenge), email, digest(challenge + ':' + code), now + 600))
        if limited:
            raise RateLimitError('Подожди минуту перед повторной отправкой; максимум 5 писем в час.')
        return challenge, code

    def cancel_code(self, challenge):
        with self.db() as db:
            db.execute('DELETE FROM login_codes WHERE challenge_hash=?', (digest(challenge),))

    def consume_code(self, email, challenge, code):
        valid = False
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM login_codes WHERE challenge_hash=? AND email=?',
                             (digest(challenge), email)).fetchone()
            if row and row['expires_at'] > time.time() and row['attempts'] < 5:
                db.execute('UPDATE login_codes SET attempts=attempts+1 WHERE challenge_hash=?', (digest(challenge),))
                valid = hmac.compare_digest(row['code_hash'], digest(challenge + ':' + code))
                if valid:
                    db.execute('DELETE FROM login_codes WHERE challenge_hash=?', (digest(challenge),))
        return valid
