# Маршрутизация пакетов KALIOPA 1.44.2.41

Документ описывает, как пакет от приложения на этом устройстве попадает на
конечный сервер: кто выбирает маршрут, какие локальные порты участвуют, что
происходит на каждом узле и где путь заканчивается. Версия — `1.44.2.41`,
проверено на живой сборке 2026-11-09.

## 1. Две независимые плоскости

```
Прокси-трафик приложений                    Перехваченный трафик
(Brave/Chrome/Discord/WhatsApp)             (NovaWFP / NovaDivert / WinDivert)
        │                                           │
        ▼                                           ▼
  системный PAC 1369                    nova_routing_backends.py
        │                               nova_transport_plans.py
        ▼                                           │
  токен прокси из PAC                               │
        └──────────────┬────────────────────────────┘
                       ▼
             слоты 1370 / 1371 / DIRECT
```

- **PAC-плоскость** — приложения, которые умеют системный прокси (Chromium,
  Discord, WhatsApp, WinHTTP-клиенты). Они получают PAC по
  `http://127.0.0.1:1369/nova.pac` и сами идут в выбранный локальный прокси.
- **Перехват** — приложения, которые прокси не понимают. Их TCP/UDP забирает
  WFP/Divert-слой и передаёт в те же слоты через `nova_transport_plans.py`.
- **Telegram Desktop** — отдельная плоскость: он не использует PAC, а явно
  ходит в SOCKS5 `127.0.0.1:1372` (релей).

## 2. Полный путь браузера

```
Chrome / Edge / Discord / WhatsApp
        │  HTTPS к example.com
        ▼
WinINET / WinHTTP
        │  AutoConfigURL = http://127.0.0.1:1369/nova.pac
        ▼
PAC 1369  (nova.pyw::generate_pac → FindProxyForURL)
        │  возвращает, например:
        │  "SOCKS5 127.0.0.1:1370; PROXY 127.0.0.1:1371"
        ▼
браузер подключается к первому доступному токену
        │
        ├── SOCKS5 127.0.0.1:1370
        │       │  nova-go (CF MASQUE / WARP)
        │       │  HTTP/3 over UDP 443, SNI маскируется
        │       ▼
        │   Cloudflare edge 162.159.198.x
        │       ▼
        │   example.com:443 (TLS внутри туннеля)
        │
        ├── HTTP CONNECT 127.0.0.1:1371
        │       │  opera-proxy
        │       │  TLS/HTTP CONNECT к Opera edge 77.111.247.19:443 (NL/AMS)
        │       ▼
        │   Opera VPN edge
        │       ▼
        │   example.com:443 (TLS внутри CONNECT)
        │
        └── DIRECT
                │  ISP, при необходимости winws/DPI-bypass
                ▼
            example.com:443
```

Важно: PAC возвращает **список фолбэков**, но каждый отдельный пакет идёт
только через один выбранный сокет. Смена протокола происходит в узле
(1370 — SOCKS5/MASQUE, 1371 — HTTP CONNECT, DIRECT — ISP), а не внутри одной
связи.

### 2.1. Что решает PAC

Проверка идёт сверху вниз, первый матч выигрывает (`FindProxyForURL`):

1. `localhost`, IP-литералы, plain hostnames → `DIRECT`.
2. Режим PAC: `off` → `DIRECT`; `full` → весь трафик в выбранный слот
   (`pac_full_route = SOCKS5 127.0.0.1:1370`), кроме `pac_full_exclude`.
3. `user_direct` → `DIRECT` (пользовательский «всегда напрямую»).
4. `user_ru` → RU-маршрут, `user_eu` → EU-маршрут.
5. `eu_over_exclude` → EU-маршрут (перебивает exclude).
6. `exclude` → `DIRECT`.
7. Локальные TLD → `DIRECT`: `.ru`, `.su`, `.рф`/`xn--p1ai`,
   `.москва`/`xn--80adxhks`, `.moscow`, `.рус`/`xn--p1acf`,
   `.дети`/`xn--d1acj3b`, `.tatar`. Дополнительно — `NOVA_LOCAL_DIRECT_TLDS`.
8. Явные режимы приложений (`discord`/`telegram`/`whatsapp`/`ai_apps` ≠ auto)
   → их маршрут.
9. `ai_primary` (Google AI: Gemini, AI Studio, NotebookLM, Flow, Jules и их
   `*.googleapis.com`; плюс `opencode.ai` и `crbug.com`/`issues.chromium.org` —
   Chromium bug tracker) → строка `ai_apps` (Opera EU, живой адрес пула —
   сейчас `77.111.247.19`, NL). Основной слот — только запасной путь, если
   вторичный слот лёг. Правило стоит **раньше** `ai_apps`. Замер 2026-11-08:
   живой EU-адрес отдаёт Gemini `200` без `/sorry`, ChatGPT `200`,
   Google-поиск без капчи; WARP с GeoIP RU сайт грузит, но панель Chrome
   регион не принимает. Пул ротирует адреса: `.244.47` днём был чистым,
   к 18:06 умер.
10. AI-домены: `ai_apps` (в текущей сборке `opera`) → 1371; `ai_unlock`/NRPT
    работают отдельно.
11. `eu` (`list/second.txt`) → EU-маршрут.
12. `youtube` (`list/youtube.txt`) → YouTube-маршрут.
13. `ru` (`list/main.txt`) → RU-маршрут.
14. `discord`, `telegram`, `whatsapp` → профильные маршруты.
15. Cloudflare-IP fallback (`ip/cloudflare.txt`) → RU-маршрут.
16. `foreign_default` → RU-маршрут (VPN), если не выключен
    `NOVA_PAC_FOREIGN_VPN_DEFAULT=0` / `"foreign_default":"direct"`.

### 2.2. Текущие значения маршрутов (live)

| Категория | Токен PAC |
|---|---|
| RU (main.txt, auto/fallback) | `SOCKS5 127.0.0.1:1370; PROXY 127.0.0.1:1371` |
| EU / YouTube | `PROXY 127.0.0.1:1371; SOCKS5 127.0.0.1:1370` |
| AI-приложения (`ai_apps=opera`) | `PROXY 127.0.0.1:1371` |
| Google AI / `opencode.ai` (secondary поднят) | `PROXY 127.0.0.1:1371` (Opera EU, NL) |
| Google AI / `opencode.ai` (secondary лёг) | `SOCKS5 127.0.0.1:1370` |
| `.ru`, `exclude`, локальные TLD | `DIRECT` |
| Остальной мир (`foreign_default`) | RU-маршрут → VPN |
| Резервы Tor/VLESS | в PAC не попадают, пока вторичный слот не переключён на них явно |

Проверка: `python tools/route_policy_check.py` → `policy OK: PAC
1370/1371/DIRECT, Telegram WARP, Tor/VLESS reserve`.

## 3. Слоты и что за ними стоит

### Основной слот — SOCKS5 127.0.0.1:1370

Один backend за раз, выбирается в `temp/profile-selection.json`:

| Backend | Что делает |
|---|---|
| **Cloudflare MASQUE** (текущий) | `nova-go`: SOCKS5 → HTTP/3 MASQUE over UDP 443 → Cloudflare edge |
| Cloudflare AWG | `wireproxy-awg`: SOCKS5 → AmneziaWG → Cloudflare |
| Proton AWG | `wireproxy-awg`: SOCKS5 → AmneziaWG → Proton |
| VLESS | `nova-xray`: SOCKS5 → VLESS/REALITY → edge |
| Custom AWG | `wireproxy-awg` с пользовательским конфигом |

Сейчас: `MASQUE/Cloudflare MASQUE 2`; выход **RU**, поэтому EU-сайты через него
не отправляются (см. таблицу EU).

### Вторичный слот — один из трёх

| Режим | Локальные порты | Куда |
|---|---|---|
| **Opera** (текущий) | HTTP `1371` | `opera-proxy` → Opera edge `77.111.247.19:443` (NL/AMS) |
| Tor (резерв) | SOCKS5 `1375`, HTTP `1378` | Tor network, только TCP |
| VLESS-профиль (резерв) | SOCKS5 `1379`, HTTP `1380` | `nova-xray` → VLESS edge |

`secondary.mode` в `temp/routing_settings.json` задаёт один из них; одновременно
живёт только один. Сейчас Opera EU, порты 1375/1378/1379/1380 закрыты.

### `last_resort`

`DIRECT` по умолчанию; при `NOVA_PAC_KILLSWITCH=1` — `SOCKS5 127.0.0.1:1`
(сознательный blackhole, чтобы не выпустить трафик напрямую при падении VPN).

## 4. Telegram: отдельный путь

```
Telegram Desktop
   │  SOCKS5 127.0.0.1:1372
   ▼
tgrelay (SOCKS5/HTTP 1372)
   │  pinned egress: warp-socks
   ▼
nova-go SOCKS5 127.0.0.1:1370
   │  MASQUE / WARP
   ▼
Cloudflare edge
   ▼
Telegram DC 149.154.167.x:443 (MTProto)
```

- `routes.telegram=warp` закрепляет релей на `warp-socks`; `opera-http` и
  Tor-HTTP для MTProto исключены.
- TLS-терминатор `127.0.0.1:1374` — helper релея (JA4/маскировка), не
  отдельный хоп и не прокси для браузера.
- Если WARP не поднят, релей не уходит в Opera/Tor/DIRECT, а ждёт/закрывает
  соединение: так MTProto не попадает в неподходящий выход.

## 5. DNS: отдельная плоскость

```
Приложение
   │  DNS UDP/TCP 53
   ▼
Windows DNS + NRPT-правила (AI-домены)
   │  каскад dns-ai → comss → geohide
   ▼
DNS-ответ приложению
```

- DNS не проходит через PAC и не занимает слоты 1370/1371.
- NRPT направляет AI-домены в разблокирующий резолвер; остальное — системный
  DNS.
- Локальный DoH `127.0.0.1:53` включается только `NOVA_DOH_GLOBAL=1`
  (`nova_doh_service` + снимок DNS-адаптеров).

## 6. Что происходит при выборе резерва

- **Tor** (`secondary.mode=tor`): браузерный EU/YouTube получает
  `SOCKS5 1375; PROXY 1378`; Telegram всё равно остаётся на WARP.
- **VLESS** (`secondary.mode=profile`): EU получает `SOCKS5 1379; PROXY 1380`;
  если VLESS выбран основным — он слушает 1370.
- **Proton AWG / CF AWG** — это primary-backend'ы на 1370; при выборе заменяют
  MASQUE, а не добавляются вторым слоем. Одновременно активен только один.
- Резервные порты не появляются в PAC, пока режим не выбран явно.

## 7. Проверка вживую

```powershell
# политика и порты
python tools/route_policy_check.py

# PAC отвечает
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:1369/nova.pac

# SOCKS5 1370 (MASQUE)
curl.exe -s -o NUL -w "%{http_code}" --socks5-hostname 127.0.0.1:1370 https://www.gstatic.com/generate_204

# HTTP 1371 (Opera)
curl.exe -s -o NUL -w "%{http_code}" --proxy http://127.0.0.1:1371 https://www.gstatic.com/generate_204

# Telegram relay: проверять живым Telegram; в логе должен быть route=warp-socks
Get-Content "$env:LOCALAPPDATA\Nova\temp\nova_console.log" -Tail 50 | Select-String "TgRelay"
```

Ожидаемо: PAC 200, SOCKS5/HTTP — 204, Telegram relay отвечает; в логе
`[TgRelay]` маршрут `warp-socks`, `502` = 0.

## 8. Текущее живое состояние (2026-11-08)

| Параметр | Значение |
|---|---|
| Версия | 1.44.2.41 |
| Основной слот | Custom/WARPgen_custom_07, SOCKS5 1370, GeoIP RU |
| Вторичный слот | Opera EU, HTTP 1371, `77.111.247.19` (NL/AMS) |
| Telegram | relay 1372 → warp-socks 1370 → DC |
| DNS | NRPT + DoH через 1370 |
| Tor / VLESS | закрыты (1375/1378/1379/1380) |
| PAC | 1369, режим hybrid, foreign_default=VPN |
| `502` в релее | 0 |

Примечание: EU-пул Opera ротирует адреса. На 2026-11-08 18:35 живой —
`77.111.247.19` (NL, AMS): Gemini/ChatGPT `200` без капчи; `77.111.244.47`
к 18:06 перестал отвечать, хотя днём был чистым. Кэш
`temp/opera_endpoint_cache.json` закрепляет живой адрес; при ротации
приложение пересобирает его через `discover`/EU-over-WARP, первый запуск
1371 может занять ~1–2 минуты.

## Схема Route Lab в программе

`resources/nova_route_spec.json` — та же цепочка, что и шаблон Route Lab;
равенство файлов проверяет `tests/test_route_spec.py`, а `snapshot.py`
обновляет обе копии. При каждой генерации PAC Nova сверяет со схемой живые
настройки и структуру скрипта и пишет расхождения строкой
`[PAC] схема Route Lab: ...`. Проверка только журналирует: маршруты она не
меняет, поэтому сбой схемы или её отсутствие не ломают PAC.

Что проверяется: порядок `user_direct`/`user_ru`/`exclude` до локальных TLD,
`FindProxyForURLEx` (WinINET), в режиме `full` — разбор `ai_apps` до
`return pac_full_route`, а при `secondary=opera` — отсутствие холодных
резервов 1375/1378/1379/1380 в PAC. `routes.browser` управляет режимом PAC:
`auto` — hybrid, `warp`/`opera` — full, `direct` — off. Схема описывает
hybrid, поэтому при `browser=warp` проверка сообщает о расхождении: eu/youtube
пойдут на 1370, а не на 1371.
