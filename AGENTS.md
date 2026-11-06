# AGENTS.md — Nova (инструкции для AI-агента)

> Правила для агентов, работающих в этом репозитории. Человеческая документация — `README.md`.
> Глубокие детали — `docs/agents/*.md`; открывай их только если задача этого касается.
> Читай этот файл первым. `nova.pyw` — 33 000+ строк: никогда не читай его целиком.

## Проверка обновлений модулей (каждая сессия)

При старте **каждой новой сессии OpenCode** и **после сжатия (compaction)**:

1. Прочитать `docs/agents/module-updates.md`.
2. Выполнить `python tools/check_module_updates.py --quiet`.
3. Если есть обновления — сообщить списком и предложить план. Не обновлять
   автоматически: backup → обновление одного модуля → тесты → живая проверка → сборка.
4. Если проверка недоступна (нет сети / GitHub rate limit) — сказать явно.

Кэш проверки — 12 часов; `--force` игнорирует кэш. Источники и процедура обновления
каждого модуля — в `docs/agents/module-updates.md`.

## Что это за проект

KALIOPA — приватный форк Nova: Windows-приложение для восстановления доступа к
заблокированным сайтам — обход DPI (zapret/winws, WinDivert), раздельная
маршрутизация (WARP/MASQUE, Opera VPN, Tor, профили), подбор стратегий обучения
(Rust-движок), Telegram-релей с нейтральным SNI.

Версия приложения: **1.44.2.30** (`resources/nova_metadata.py`); Rust workspace —
1.43.2 (`nova-rs/Cargo.toml`). Стек: Python 3.14 + tkinter (GUI), Rust 2024
(1.90+; движок/обучение/пробы/TLS), Go 1.27 (nova-go MASQUE/WARP, nova-xray VLESS/VMess/Trojan/SS), WinDivert/WFP.
Upstream: https://github.com/confeden/Nova; приватный форк: https://github.com/abonent0007/KALIOPA.

## Репозиторий ≠ установленное приложение (читать первым!)

- Этот каталог — **исходники**. Установленная программа
  `C:\Users\User\AppData\Local\Nova\Nova.exe` — **замороженная PyInstaller-сборка**.
- Правки в исходниках **не влияют** на установленную копию. Рестарт exe их не подхватывает —
  нужна пересборка (`Inno.py`).
- Артефакты сборки: `C:\Users\User\Documents\build` (вне репозитория). Staging-папка:
  `C:\Users\User\Documents\build\Inno\v<version>\Nova` (сейчас `v1.43.2\Nova\Nova.exe`);
  промежуточные файлы PyInstaller — `C:\Users\User\Documents\build\temp_inno\{dist,work}`.
- Не редактируй установленную папку напрямую (допустима только осознанная замена exe с бэкапом).

## Сборка (кратко; детали — docs/agents/build.md)

- Полный установщик: `py Inno.py` — требует Python 3.14 + PyInstaller, Go 1.26, Inno Setup 6,
  сестринский репозиторий `Nova Android` (для `replace` в go.mod), `bin/`, `profiles/`.
- Android-форк: `C:\Users\User\Documents\Nova-Android-Fork`; для `replace` создан junction
  `C:\Users\User\Documents\Nova Android`. Зависимости Go — `tools/deps/fetch_go_deps.sh` в Android-форке.
- Только staging (без установщика): те же шаги, но с env-флагами
  `NOVA_SKIP_NOVA_GO=1 NOVA_SKIP_NOVA_XRAY=1 NOVA_SKIP_NOVA_ENGINE=1 NOVA_SKIP_TLS_TERMINATOR=1 NOVA_SKIP_LIST_SYNC=1`,
  запуск через Python 3.14:
  `& "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe" Inno.py`.
  `NOVA_KEEP_STAGING=1` — не удалять staging после сборки установщика.
- PyInstaller 6.19 + Python 3.14: `distutils` НЕ должен быть в `PYI_EXCLUDED_MODULES`
  (локальный фикс; иначе `ValueError: Target module "distutils" already imported as ExcludedModule`).
- `bin/` и `icon.ico` в upstream отсутствуют: `bin/` копируется из установки
  (`AppData\Local\Nova\resources\bin`), `icon.ico` извлекается из `Nova.exe`.

## Запуск и отладка

- Одновременно — **только один экземпляр** (порты 1369–1380, WinDivert/WFP). Выход — через трей,
  не убивать процесс принудительно (оставит системный прокси/маршруты).
- PAC: `http://127.0.0.1:1369/nova.pac` (перегенерируется при изменениях; прописывается в реестр).
- Порты: **1369** PAC · **1370** основной SOCKS5 (WARP/MASQUE/VLESS) · **1371** вторичный HTTP
  (Opera; Tor — 1375/1378, импортированный профиль — 1379/1380) · **1372** Telegram-релей ·
  **1374** слушатель TLS-терминатора.
- Temp/логи: `<app>\temp\` (`nova.pac`, `tls_terminator.log`, `*.pid`).
- Быстрые проверки:
  `curl.exe -s -o NUL -w "%{http_code}" --socks5-hostname 127.0.0.1:1370 https://www.gstatic.com/generate_204` (204),
  `curl.exe ... --proxy http://127.0.0.1:1371 ...` (204), затем проверить правила в PAC.

## Карта кода (детали — docs/agents/architecture.md)

| Область | Где |
|---|---|
| GUI, PAC, маршрутизация, оркестрация | `nova.pyw` (якоря: `generate_pac` ~8461, `FindProxyForURL` ~8964) |
| Решения транспорта по приложениям | `resources/nova_routing_backends.py` |
| Цепочки попыток TCP (warp/opera/direct) | `resources/nova_transport_plans.py` |
| Синхронизация списков | `resources/nova_list_sync.py` |
| Профили: Proton, VLESS, подписки | `resources/nova_proton.py`, `nova_vless.py`, `nova_subscriptions.py`, `nova_issuance.py` |
| Rust-движок/обучение/пробы/TLS | `nova-rs/crates/*` (core, learn, probe, zapret, tls, tgrelay, tgrelay-net, health, cloudflare, cli) |
| Стратегии winws | `strat/*.json`; маски ClientHello/QUIC — `fake/*.bin`; версии движка и zapret2 — `docs/agents/engine-upgrades.md` |
| Документы по узлам/DNS | `docs/agents/state-2026-10-31.md`, `dns-unblock.md`, `proton-and-vless.md`, `zapret2.md` |
| Домены/IP | `list/*.txt`, `ip/*.txt` |
| Профили окружения | `profiles/` (AWG Proton, AWG Cloudflare, Custom, MASQUE, VLESS) |
| Решения | `docs/adr/0001..0004` |

## Модель маршрутизации (кратко; детали — docs/agents/routing.md)

Порядок правил PAC (1.43.2 + локальные патчи):
`user_direct → user_ru → user_eu → eu_over_exclude → exclude → локальные TLD
(.ru/.su/.рф/…) → DIRECT (наш патч) → явные режимы приложений → AI-домены → eu → youtube →
ru → discord → telegram → whatsapp → Cloudflare-IP fallback →
foreign-default (наш патч, по умолчанию VPN)`.

- `list/main.txt` — RU-список (блокировки DPI → туннель), `list/second.txt` — EU (гео → зарубежный
  выход), `list/exclude.txt` — всегда DIRECT; также `ai/cloudflare/youtube/telegram/whatsapp/discord/games/rkn`.
- Ключевые env: `NOVA_PAC_KILLSWITCH=1` (закрывать при падении VPN), `NOVA_PAC_FOREIGN_VPN_DEFAULT=1`
  (по умолчанию: весь не-локальный трафик через VPN; `=0` — DIRECT),
  `NOVA_LOCAL_DIRECT_TLDS=.by,.kz` (доп. локальные зоны к `.ru/.su/.рф/...`),
  `NOVA_DNS_CACHE_TTL=300` / `NOVA_DNS_NEGATIVE_TTL=60` (TTL DNS-кэша, секунды),
  `NOVA_PROFILE_ROTATION=0` (отключить авторотацию узлов профиля),
  `NOVA_ROUTING_BACKEND=auto|current|public-hybrid|windivert-hybrid`.

## Локальные модификации (не из upstream) — при обновлении исходников переприменить

1. **PAC локальные TLD → DIRECT** (`.ru`, `.su`, `.рф`/punycode, `.москва`, `.moscow`, `.рус`,
   `.дети`, `.tatar`) + опция `foreign_default` (`nova.pyw`, `generate_pac`,
   `resources/nova_local_direct.py`).
2. **`Inno.py`: `distutils` удалён из `PYI_EXCLUDED_MODULES`** (баг PyInstaller 6.19 на Python 3.14).
3. **`Inno.py`: повторная сборка в существующий staging** (`dirs_exist_ok=True`) и нейтральный
   `routing_settings.json` при отсутствии источника — иначе clean build падает на копировании/ISS.
4. Рабочие артефакты сборки: `bin/` (из установки), доп. `profiles/`, `icon.ico`. Не коммитить.
5. **`foreign_default` по умолчанию VPN**: весь не-.ru трафик без совпадений → VPN/прокси;
   `NOVA_PAC_FOREIGN_VPN_DEFAULT=0` / `"foreign_default":"direct"` — откат.
6. **Seed-стратегии обфускации** в `strat/general.json`: Google TLS/QUIC, `sniext`, VK kyber.
7. **Security backport** (`nova.pyw`): self-deletion и admin relaunch без `shell=True`
   (`--cleanup-old-exe`, `subprocess.list2cmdline`).
8. **Relay identity dynamic** (`nova.pyw` + `resources/nova_relay_identity.py`): логин
   `nova-pc-<version>` собирается из версии, под которую выпущен `profiles/opera_relay.key`,
   а не из `CURRENT_VERSION` и не из константы. Модуль берёт версии из релизов upstream,
   проверяет ключ пробой через WARP и кэширует рабочую версию в `temp/relay_identity.json`
   и `profiles/opera_relay.version`. При ротации ключа обновить файл ключа; версия
   определится сама, при необходимости — `NOVA_RELAY_KEY_VERSION`.
9. **Брендинг KALIOPA**: отображаемое имя — `KALIOPA` (заголовок окна, сплэш, трей, меню
   «Перезапустить KALIOPA», диалоги, `MyAppName` в `NovaInstaller.iss`); фон — `img/background.png`
   (генерируется `tools/make_background.py`, встраивается в exe при сборке). Имена exe/папки/
   мьютекса/процессов и пути AppData остаются `Nova` — их менять нельзя, иначе сломаются
   обновления, хелперы и существующая установка.

## Обновления

- Списки: `nova_list_sync.sync_from_network` — `manifest.json` + sha256 из `confeden/nova_updates/nova_pc`
  через зеркала (raw.githack, raw.githubusercontent, jsdelivr) и прокси; выполняется при старте
  установленной сборки. В личном форке обновлять через `nova_list_sync`; **не запускать
  `list_publish.py`** — он коммитит и пушит списки в `confeden/nova_updates`.
- Профили: Proton issuance (`nova_proton/nova_issuance`), подписки (`nova_subscriptions`).
  Ключи `tgrelay/cf_ws.key` и `awg/opera_relay.key` намеренно отсутствуют upstream (инфраструктура автора).

## Обфускация и SNI

- winws-стратегии: multisplit/fakeddisorder/hostfakesplit, `fake-tls-mod rnd/rndsni/dupsid/padencap`,
  `split-pos=sniext`, fake QUIC; маски — `fake/*.bin` (есть kyber-hello для vk/rutracker).
- TLS-терминатор (`nova-tls`) с JA4-профилями chrome/firefox/yandex для TG-релея; нейтральный SNI
  (`www.` своей зоны) — ADR 0004; классификация отказа туннеля по фазам — ADR 0003.
- Известный пробел: kyber-маски не используются в сидах `strat/*.json`; `sniext` — только в cloudflare/discord.

## Тесты и проверки

- `python -m py_compile nova.pyw`; `python -m unittest discover -s tests -p "test_*.py"` (66 тестов).
- `python tools/static_analysis.py` — замена линтера: неиспользуемые импорты, инвентарь
  статических значений, внешние вызовы без `try`. Детали — `docs/agents/static-analysis.md`.
- Rust (из `nova-rs/`): `cargo test --workspace`; TLS-формы: `cargo test -p nova-tls --features shape`;
  таблица фаз: `NOVA_UPDATE_PHASE_TABLE=1 cargo test -p nova-probe --test table`.
  CI выполняет оба основных прогона: `.github/workflows/build_tls_terminator.yml`.
- Release-профиль (`nova-rs/Cargo.toml`): не менять `panic = "unwind"` — паника пробы не должна
  ронять процесс, который останавливает winws и восстанавливает системный прокси.
- После изменений: PAC жив, 1370/1371 отвечают 204, для `.ru` прямой путь быстрее туннелей
  (замер 2026-10-18: 167–432 мс direct против 460–810 мс через туннели).
- Перед правками — бэкап: `C:\lib\backup-nova\` (pre/post zip).

## Личный локальный форк

- Это локальный форк **только для личного использования**. Не публиковать его и не пушить
  в публичные репозитории.
- `upstream` = https://github.com/confeden/Nova (ветка `main`), рабочая ветка — `personal`.
- Обновление upstream: `git fetch upstream`, затем `git log --oneline personal..upstream/main`
  и merge/rebase в `personal`.
- Источники списков и профилей остаются стоковыми: не менять `nova_list_sync`, `nova_proton`,
  `nova_subscriptions`, `nova_issuance` и адреса ресурсов обновления.
- Версия форка — `CURRENT_VERSION = "1.43.2.N"` в `resources/nova_metadata.py`;
  перед новой сборкой: `python tools/bump_fork_version.py`.
- Автообновление самой программы отключено (`UPDATE_URL = ""`, кнопка скрыта, updater
  выходит сразу). Из сети остаются только списки и профили; не включать upstream updater.
- При сбое обновления профилей или смене сервера смотреть изменения upstream только в
  profile-update коде: `powershell -ExecutionPolicy Bypass -File tools/check_upstream_profile_updates.ps1 -Diff`;
  переносить вручную, не меняя стоковые адреса.
- Локальные профили (кроме стокового `profiles/AWG Proton/proton_nodes.json`), `bin/`, `temp/`,
  `.opencode/`, сборки и секреты не коммитятся (`.gitignore`).
- Сборка — в `C:\Users\User\Documents\build`.

## Границы

- Не запускать два экземпляра; не убивать Nova принудительно; выход — через трей.
- Не коммитить секреты/ключи; не публиковать `bin/`; соблюдать `THIRD_PARTY_NOTICES.md`.
- Не менять дефолты маршрутизации «по вкусу»: сначала замеры (blockcheck/live-probes), потом правки.
- Трудные задачи: сначала второе мнение (Council/Google AI), затем локальная верификация.

<!-- Added: 2026-11-01 -->
## ChatGPT / Opera routing (2026-11-01)
ChatGPT web is unreachable via Cloudflare WARP, Tor and direct RU (403), but loads in a real headed browser through the Opera VPN secondary slot (EU, exit SE). Nova must keep `secondary.mode=opera`, `opera_region=EU`, and `routes.ai_apps=opera`; Opera bootstrap must skip dead relays, try direct discover before the published feed, and always use `-server-selection fastest`. MTProto must never use `opera-http` or Tor HTTP egress. Full measurements: docs/agents/chatgpt-opera.md; build state: docs/agents/state-2026-11-01.md.
