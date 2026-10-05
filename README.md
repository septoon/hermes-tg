# Hermes через AITunnel

Hermes Agent v0.21.5 (релиз v2026.9.24) подключён как подмодуль официального
[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).
Модель: `deepseek-v4-flash-0731`, OpenAI Chat Completions через AITunnel.

## Установка

```bash
git clone --recurse-submodules https://github.com/septoon/hermes-tg.git
cd hermes-tg
./scripts/install.sh
```

Запиши отдельный ключ AITunnel в созданный `.env`:

```dotenv
AITUNNEL_API_KEY=
```

```bash
./hermes doctor
./hermes
```

Установка использует Python 3.13, зависимости с проверкой хешей из официального
`uv.lock`, CLI, web dashboard и библиотеки мессенджеров. Локальный браузер, Computer Use,
десктопный интерфейс и внешние платные инструменты не устанавливаются.
Инструменты CLI: терминал, файлы, навыки, память, список задач.
Лимит агентного цикла — 30 шагов. Telegram использует `TELEGRAM_BOT_TOKEN`
и числовые Telegram user ID в `TELEGRAM_ALLOWED_USERS` (через запятую).
Обе переменные хранятся в `.env`. Не включай открытый доступ ко всем пользователям.
Инструменты Telegram совпадают с CLI, дополнительно доступен планировщик задач.
В `config.yaml` указан проверенный резервный IP Telegram API: основной адрес
недоступен из сети VPS. Hermes сохраняет проверку TLS для `api.telegram.org`.

## Конфигурация и секреты

- `config.yaml` — исходная конфигурация без секретов.
- `.hermes/config.yaml` — активная конфигурация; создаётся при установке.
- `.env` — ключи, права доступа `600`; `.hermes/.env` ссылается на него.
- `.hermes/` — локальная история, логи, память и служебные файлы.

`.env`, активный профиль и артефакты исключены из Git. В публичный репозиторий
попадают только конфигурация, скрипты и ссылка на официальный код.
Не добавляй секреты в YAML, README, команды с аргументами или исходники.

```bash
git config core.hooksPath .githooks
python3 scripts/check-secrets.py --history
git check-ignore .env .hermes/.env .hermes/config.yaml
```

Установщик включает hooks перед commit/push. Проверка блокирует личные файлы,
известные форматы ключей и точные значения секретов из `.env`. Она не заменяет
проверку diff человеком. Обновляй подмодуль и lockfile осознанно: автоматическое
обновление через `hermes update` меняет закреплённую здесь версию.

На VPS запускай Hermes отдельным пользователем `hermes` без sudo.
Ключ доставляется отдельно по SSH и не хранится в GitHub.

Для фонового запуска без dashboard предусмотрен `deploy/hermes-tg.service`.
При использовании dashboard gateway установлен штатной командой Hermes как
пользовательский systemd-сервис с `loginctl enable-linger hermes`; это позволяет
панели запускать, останавливать и перезапускать бота без sudo. Drop-in
`deploy/hermes-gateway-limits.conf` ограничивает сервис одним CPU и 768 МиБ памяти.
Два варианта сервиса нельзя запускать одновременно с одним токеном бота.
Без настроенного мессенджера gateway обслуживает только планировщик задач;
чат доступен через CLI. На Mac фоновый сервис не устанавливается.

## Web dashboard

Панель на `https://hermes.lumastack.ru` использует тот же `HERMES_HOME`, что и
Telegram gateway: модель, настройки Telegram, память, навыки, сессии и cron общие.
Dashboard запускается отдельным сервисом от пользователя `hermes` на loopback
`127.0.0.1:9119`; nginx обслуживает HTTPS и WebSocket.

Основной вход — одноразовый код на адрес из `HERMES_LOGIN_EMAIL`. Другие адреса
не получают письма или доступ. Код действует 10 минут, имеет пять попыток и
используется один раз. Повторная отправка — через минуту, максимум пять писем в час;
ограничения сохраняются после перезапуска. Отправка использует SMTP с проверкой TLS.
`TELEGRAM_ALLOWED_USERS` содержит один уже подтверждённый ID владельца, связанный
с этой почтой: dashboard и Telegram-бот используют тот же аккаунт и профиль.

Сессия dashboard хранится в `.hermes/dashboard-sessions.sqlite3` с правами `0600`.
Сервер не завершает её по времени. Выход отзывает сессию, удаление владельца из
настроек также закрывает доступ. В базе находятся только хеши токенов и кодов.
Cookies — HttpOnly, Secure, SameSite=Lax; очистка cookies или ограничения их хранения
самим браузером потребуют нового входа. Перезапуск сервиса сессию не сбрасывает.

Если `HERMES_LOGIN_EMAIL` не задан, доступен Telegram OIDC (authorization code +
PKCE). Плагин проверяет подпись ID token, issuer, audience, срок и разрешённый ID,
после чего создаёт собственную долговременную сессию dashboard. Короткий срок
Telegram ID token не используется как срок сессии панели.

В BotFather → Login Widget настрой Redirect URI
`https://hermes.lumastack.ru/auth/callback`. Client ID и Client Secret хранятся
в `.env` как `HERMES_TELEGRAM_OIDC_CLIENT_ID` и
`HERMES_TELEGRAM_OIDC_CLIENT_SECRET`; это отдельные credentials, не токен бота.

Сборка UI по официальному lockfile:

```bash
./scripts/build-dashboard.sh
```

Для VPS нужны только `hermes-agent/hermes_cli/web_dist` и
`hermes-agent/ui-tui/dist` — node_modules переносить не требуется.
Сборки и ключи исключены из Git. Шаблоны nginx и systemd находятся в `deploy/`.
Email-форма и отправка кодов работают в отдельном `hermes-login.service` на
loopback `127.0.0.1:9120`. Cookies, проверка сессий и WebSocket остаются штатными
механизмами Hermes; nginx направляет только `/login` и отправку кода в этот сервис.
Сертификат выпускается certbot webroot, продление обслуживает системный timer.
Из сети VPS OAuth Telegram доступен через `149.154.167.220`; scoped запись
`oauth.telegram.org` в `/etc/hosts` сохраняет TLS/SNI и проверку сертификата.
