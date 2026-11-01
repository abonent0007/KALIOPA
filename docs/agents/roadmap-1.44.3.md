# План 1.44.3: все незакрытые пункты, исследование → реализация → проверка

Каждый пункт проходит три шага: **investigate** (собрать факты, замерить), **implement**
(минимальная правка с тестом), **verify** (живая проверка на этой машине).

Статус на 2026-11-01, сборка **1.44.2.10** (четвёртая цифра — номер форка; upstream 1.44.2).

## Фаза A. Релей Telegram — ЗАКРЫТА

### A1. Запрет MTProto через Tor-HTTP — СДЕЛАНО
- investigate: 49 × `502 Bad Gateway (tor protocol violation)`, `route=opera-http` указывал на Tor (1378).
- implement: при закрытом 1371 маршрут `opera-http` исключается для Telegram (`tgrelay/transparent_relay.py`).
- verify: 1.44.2.9, `502` = **0** (было 49).

### A2. `InvalidStateError` в proactor-loop — ЗАКРЫТО БЕЗ ПРАВКИ ЛОГИКИ
- investigate: защита уже есть (`transparent_relay.py:2400–2470`): retry до `_LOOP_RESUME_LIMIT`,
  туннели сохраняются. Строка в журнале — сообщение о сработавшей защите.
- implement: пересоздание цикла запрещено (уронило бы туннели); уровень лога не менялся.
- verify: 2 записи за сессию, падений нет.

### A3. Маршрут по скорости + даунгрейд логов — СДЕЛАНО
- investigate: строка собиралась в `_traffic_stats_loop` (`transparent_relay.py:1648`), не в `nova.pyw`;
  писалась каждые 8 с на соединение; порядок маршрутов был фиксированным.
- implement: EWMA скорости по маршруту (`_note_route_speed`, `temp/tgrelay_routes.json`, TTL 24 ч),
  сортировка прокси-кандидатов (`_order_attempts_by_speed`, внутри health-бакетов `_order_native_attempts`),
  агрегация `traffic` — одна строка на маршрут раз в 60 с (`NOVA_TG_RELAY_TRAFFIC_LOG_INTERVAL`),
  `probe diag` — не чаще 30 с (`NOVA_TG_RELAY_PROBE_DIAG_INTERVAL`). `direct` никогда не поднимается.
- verify: тесты `tests/test_route_speed.py` (8), лог после сборки.

## Фаза B. Узлы — ЗАКРЫТА

### B1. Proton-варианты в обновление профилей — СДЕЛАНО
- implement: `nova_proton.variant_files()` пишет до 3 конфигов на узел (`-p2`, `-p3`, другие порты
  из 443/1194/4500 и свои junk-наборы), имена входят в `generated_files`, страны считаются по файлам.
  Выключатель `NOVA_PROTON_VARIANTS=0`. `GENERATED_NAME_RE` понимает суффикс `-pN` (уборка/страна).
- verify: `tests/test_proton_variant_files.py` (5); 50 узлов → до 150 файлов.

### B2. Opera backoff — СДЕЛАНО
- investigate: перезапуск каждые 15 с после серии из 4 неудач, лог раз в 45 с.
- implement: `opera_restart_fail_streak`, пауза `60·2^n` (5 с в стартовом окне), максимум 30 мин.
- verify: `[EU]`-строки реже; после успеха счётчик сбрасывается.

### B3. VLESS pre-flight при импорте — СДЕЛАНО
- investigate: 26 из 40 узлов мертвы по TCP; TLS-проба напрямую ловит DPI на SNI и отвергала бы
  рабочие через WARP узлы.
- implement: `nova_vless_preflight` — TCP-коннект (2 с, 8 потоков) для новых узлов подписки до записи;
  TLS — опция `NOVA_VLESS_PREFLIGHT_TLS=1`; выключатель `NOVA_VLESS_PREFLIGHT=0`. Отсеянные не попадают
  в `identities` и квоту.
- verify: `tests/test_vless_preflight.py` (5), живой импорт подписки после сборки.

## Фаза C. DNS и логи — ЗАКРЫТА

### C1. DoH-адаптеры — СДЕЛАНО (опция)
- implement: `nova_dns_adapters` (снимок/восстановление через PowerShell, файл-страховка),
  `nova_doh_service` (резолвер 127.0.0.1:53, upstream = прежний DNS, восстановление при выходе
  и после падения). Включение `NOVA_DOH_GLOBAL=1`, по умолчанию выключено (NRPT остаётся основным).
- verify: `tests/test_doh_service.py` (10); живой снимок адаптера (индекс 18, DNS 10.107.208.175);
  резолвер на 15353 ответил `example.com` (rcode 0, 2 A).

### C2. ICMP→HTTP fallback — ЗАКРЫТО КАК ЕСТЬ
- investigate: `nova_ping.probe_host` уже делает ICMP первым и TCP-фолбэк с бюджетом 1.2 с.
  HTTP-проба узла до подключения измеряет не узел, а DPI, поэтому не добавлялась.
- verify: `tests/test_ping_fallback.py` (3).

### C3. Агрегация трафик-логов — СДЕЛАНО (в A3).

## Фаза D. Внешние выходы — ЗАБЛОКИРОВАНО ВНЕШНИМИ УСЛОВИЯМИ

### D1. ChatGPT не через WARP — СДЕЛАНО
- investigate: OpenAI 403 на WARP, Tor и direct; headed Chrome через Opera SE
  (77.111.247.19) загружает ChatGPT полностью, curl/headless получают только JS-челлендж.
- implement: Opera запускается через direct discover с `fastest`, мёртвые relay и
  опубликованные endpoint'ы пропускаются, успешный endpoint кэшируется; `ai_apps → opera`
  в PAC; MTProto исключён из `opera-http`.
- verify: 1.44.2.12, системный PAC + headed Chrome: ChatGPT, Gemini, YouTube открываются.
  Детали и замеры endpoint'ов — `docs/agents/chatgpt-opera.md`.

### D2. VPS + nova-connect — БЛОК
- нужен VPS/аккаунт и деплой Worker; без него проверка «2ip = страна VPS» невозможна.

### D3. Flow Unlocker-компаньон — БЛОК
- расширение патчит RPC Google в браузере; в ядро не встраивается, проверка требует загрузки
  расширения в Chrome вручную.

## Фаза E. Полировка

### E1. Гигиена процессов — СДЕЛАНО
- implement: `nova_process_hygiene.kill_orphans` (CIM, возраст >10 мин) в фоне на старте;
  `winws_test` не переиспользуется (у каждого свой WinDivert-фильтр), осиротевшие снимаются.
- verify: `tests/test_process_hygiene.py` (6); на живой 1.44.2.10 одновременно живут 3 коротких
  `winws_test` (10–40 с) — это активные проверки стратегий, а не утечка; порог 10 минут их не трогает.

### E2. Точный фон — БЛОК
- присланное фото не сохранилось на диск; генератор image-gen заблокирован политикой.
  `img/background.png` уже используется как есть — достаточно положить файл и пересобрать.

### E3. Лок-файлы установщика — СДЕЛАНО
- implement: `tools/install_overlay.ps1` — штатное закрытие, robocopy, точечная копия
  `Nova.exe`/`libcrypto-3.dll`/`select.pyd` с переименованием занятого файла и повтором.
- verify: этой сборкой поставлена 1.44.2.10 — `[overlay] copied OK`, без диалогов и ошибок.

## Живая проверка 1.44.2.12 (2026-11-01)

- окно `OBNOVA v1.44.2.12`, лог `VERSION: 1.44.2.12`;
- `502 / protocol violation`: **0**; Telegram native — `warp-socks`;
- порты: 1369, 1370, 1371 (Opera), 1372, открыты; 1375/1378 закрыты (вторичный слот — Opera);
- Opera: cached endpoint `77.111.247.19:443`, `1371 готов` за ~1 с, выход SE;
- PAC + headed Chrome: **ChatGPT загружается**, Gemini и YouTube открываются;
- тесты: **160 OK**, `py_compile` PASS, статанализ: 0 неиспользуемых импортов, 0 незащищённых вызовов данных.

## Живая проверка 1.44.2.10 (2026-11-01)


- окно `OBNOVA v1.44.2.10`, лог `VERSION: 1.44.2.10`;
- `502 / protocol violation`: **0**;
- порты: 1369, 1370, 1372, 1375, 1378 открыты; 1371 закрыт намеренно (вторичный слот — Tor);
- SOCKS5 1370 → `generate_204` = **204**;
- PAC: RU `1370 → 1375 → 1378`, YouTube `1370 → 1375 → 1378`;
- ошибок/трейсбеков в журнале: **0**;
- тесты: **160 OK**, `py_compile` PASS, статанализ: 0 неиспользуемых импортов, 0 незащищённых вызовов данных.

