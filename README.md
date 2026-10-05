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

## Chronicle: локальный семантический поиск на VPS

На VPS память обслуживает Chronicle 5.8.35 с Ollama 0.35.1 и
`chronicle-embeddinggemma` — локальным именем модели
[`embeddinggemma:300m-qat-q4_0`](https://ollama.com/library/embeddinggemma:300m-qat-q4_0).
Многоязычная модель выдаёт векторы размером 768; на сервере проверен поиск русских
перефразировок после перезапуска Chronicle. Контекстный движок остаётся
`compressor`. Встроенные MEMORY.md/USER.md и история сессий сохранены;
массовый импорт прежних диалогов в Chronicle не выполнялся.

`deploy/hermes-ollama.service` запускает отдельный процесс без sudo на
`127.0.0.1:11434`: предел RAM 512 МиБ, мягкий порог 384 МиБ, запрет swap для
Ollama, половина одного CPU, одна модель и один параллельный запрос.
Модель выгружается через 10 секунд без запросов; маленький сервер продолжает
работать. `deploy/chronicle-embeddings.Modelfile` задаёт batch 32 и один поток.
`deploy/chronicle-memory.yaml` ограничивает вход до 512 оценочных токенов и
включает фоновую обработку четырёх заданий на ход. При отказе endpoint текст
сохраняется, embeddings откладываются, поиск продолжает работать через FTS;
автоматического перехода к hashing нет.

Замер 06.10.2026: CPU-only Ollama занимает 60 МиБ диска, модель — 228 МиБ;
пик памяти сервиса — 385 МиБ. После выгрузки осталось около 13 МиБ анонимной
памяти и 58–82 МиБ освобождаемого файлового кеша. Холодный запрос занял
2,7 секунды, следующие — 0,1–0,6 секунды. Это функциональный замер, не
проверка будущих пиков всех сервисов. Swap системы уже был занят: 940 МиБ до
установки, 1063 МиБ после распаковки и тестов; Ollama swap не использует.

Для повторной установки на этом VPS используются CPU-only файлы официального
архива. Команды выполняются администратором сервера из каталога проекта:

```bash
mkdir -p /opt/hermes-ollama
curl -fL https://github.com/ollama/ollama/releases/download/v0.35.1/ollama-linux-amd64.tar.zst \
  -o /var/tmp/hermes-ollama-0.35.1.tar.zst
tar --zstd --exclude='lib/ollama/cuda*' --exclude='lib/ollama/vulkan*' \
  -xf /var/tmp/hermes-ollama-0.35.1.tar.zst -C /opt/hermes-ollama
rm /var/tmp/hermes-ollama-0.35.1.tar.zst
id hermes-ollama || useradd --system --home-dir /var/lib/hermes-ollama \
  --shell /usr/sbin/nologin hermes-ollama
install -m 644 deploy/hermes-ollama.service /etc/systemd/system/hermes-ollama.service
systemd-analyze verify /etc/systemd/system/hermes-ollama.service
systemctl daemon-reload
systemctl enable --now hermes-ollama
/opt/hermes-ollama/bin/ollama pull embeddinggemma:300m-qat-q4_0
/opt/hermes-ollama/bin/ollama create chronicle-embeddinggemma \
  -f deploy/chronicle-embeddings.Modelfile
```

Для распаковки нужен `zstd`; временный архив требует ещё около 1,4 ГБ диска.
Проверенный digest модели:
`ad34f3f2e277727ddc8faa2a4752b2a482f641e996b44f6106d18b9175b6eaf4`.
Chronicle устанавливается командой `hermes plugins install chronicle` из каталога
Hermes. Затем включите `chronicle` в `plugins.enabled` и объедините секцию
`memory` из `deploy/chronicle-memory.yaml` с активным `.hermes/config.yaml`,
сохранив остальные настройки. Перед переключением сделайте резервные копии
конфигурации и SQLite при остановленных gateway/dashboard. Полный `git_repo`
нужен потому, что Chronicle разворачивает `~` относительно HOME, а не HERMES_HOME.
Одна форма embeddings в панели не заменяет вложенную runtime-конфигурацию.
После переключения перезапустите gateway/dashboard.

Проверка выгрузки через 10 секунд после последнего embedding:

```bash
systemctl show hermes-ollama -p MemoryCurrent -p MemoryPeak -p MemorySwapMax
curl -fsS http://127.0.0.1:11434/api/ps
```

Для отката остановите gateway/dashboard, восстановите прежние `memory` и
`plugins` из резервной конфигурации, затем запустите их и остановите Ollama.
Базу Chronicle и старые файлы памяти удалять не нужно.

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
