"""Small loopback-only login UI and email-code delivery. Hermes owns session cookies."""
import os
from pathlib import Path
import smtplib
import ssl
from email.message import EmailMessage

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
import uvicorn

from email_auth import EmailAuthProvider, RateLimitError
from hermes_cli.dashboard_auth import ProviderError
from hermes_constants import get_hermes_home

load_dotenv(get_hermes_home() / '.env')
ORIGIN = 'https://hermes.lumastack.ru'
provider = EmailAuthProvider(
    email=os.environ['HERMES_LOGIN_EMAIL'], user_id=os.environ['TELEGRAM_ALLOWED_USERS'],
)
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def send_code(address, code):
    message = EmailMessage()
    message['From'] = os.environ['HERMES_SMTP_FROM']
    message['To'] = address
    message['Subject'] = 'Код входа в Hermes'
    message.set_content(
        f'Код входа: {code}\n\nКод действует 10 минут и используется один раз.\n'
        'Сайт: https://hermes.lumastack.ru\n'
        'Если ты не запрашивал вход, проигнорируй письмо.\n'
    )
    host, port = os.environ['HERMES_SMTP_HOST'], int(os.environ['HERMES_SMTP_PORT'])
    tls = ssl.create_default_context()
    if os.environ.get('HERMES_SMTP_SECURE', 'true').lower() == 'true':
        connection = smtplib.SMTP_SSL(host, port, timeout=10, context=tls)
    else:
        connection = smtplib.SMTP(host, port, timeout=10)
    with connection as smtp:
        if not isinstance(smtp, smtplib.SMTP_SSL):
            smtp.starttls(context=tls)
        smtp.login(os.environ['HERMES_SMTP_USER'], os.environ['HERMES_SMTP_PASSWORD'])
        smtp.send_message(message)


@app.get('/login')
async def login():
    return HTMLResponse(
        Path(__file__).with_name('login.html').read_text(),
        headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'same-origin'},
    )


class CodeRequest(BaseModel):
    email: str = Field(max_length=254)


@app.post('/auth/email/send-code')
async def request_code(request: Request, body: CodeRequest):
    if request.headers.get('origin') != ORIGIN:
        raise HTTPException(403, 'Неверный источник запроса.')
    try:
        challenge = await run_in_threadpool(provider.request_code, body.email, send_code)
    except RateLimitError as exc:
        raise HTTPException(429, str(exc)) from exc
    except (smtplib.SMTPException, OSError, ProviderError) as exc:
        raise HTTPException(503, 'Не удалось отправить письмо. Попробуй позже.') from exc
    return {'challenge': challenge, 'message': 'Если адрес разрешён, код отправлен на почту.'}


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=9120, access_log=False)
