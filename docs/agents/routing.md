# Маршрутизация Nova (для агентов)

Всё, что видит браузер, решает PAC-файл, который генерируется в
`nova.pyw::generate_pac` (~L8461) и отдаётся по `http://127.0.0.1:1369/nova.pac`.
Приложение/процессы с перехватом (NovaWFP/NovaDivert/релеи) маршрутизируются отдельно —
`resources/nova_routing_backends.py` и `resources/nova_transport_plans.py`.

## Порядок правил PAC (1.43.2 + локальные патчи)

Проверка идёт сверху вниз, первый матч выигрывает (JS-функция `FindProxyForURL`):

1. `localhost`, IP-литералы, plain hostnames → DIRECT.
2. Режим PAC: `off` → DIRECT; `full` → весь трафик в выбранный слот (`pac_full_route`),
   кроме `pac_full_exclude`-исключений; явный режим приложения действует и здесь.
3. `user_direct` → DIRECT (пользовательский список «всегда напрямую»).
4. `user_ru` → RU-маршрут (VPN), `user_eu` → EU-маршрут (зарубежный выход).
5. `eu_over_exclude` → EU-маршрут (перебивает exclude).
6. `exclude` → DIRECT.
7. **`*.ru → DIRECT`** — локальный патч (пользовательские списки выше могут перебить).
8. Явно выбранные режимы приложений (discord/telegram/whatsapp ≠ auto) → их маршрут.
9. AI-ветки: `ai_second` → вторичный слот или DIRECT; `ai_region_direct` → DIRECT;
   `ai_unlock` (если нет ни одного зарубежного выхода) → DIRECT для пересечения с `eu`.
10. `eu` (second.txt) → EU-маршрут.
11. `youtube` → YouTube-маршрут (порядок зависит от зарубежности выхода основного слота).
12. `ru` (main.txt) → RU-маршрут.
13. `discord`, `telegram`, `whatsapp` → свои маршруты; Telegram-релей 1372 перебивает
    маршрут только в режиме auto.
14. Cloudflare-IP fallback: домен без совпадений, чей IP в `ip/cloudflare.txt`, → RU-маршрут.
15. **`foreign_default_route`** — локальный патч форка: по умолчанию **VPN** (RU-маршрут:
    WARP/MASQUE/VLESS → резервные слоты). `NOVA_PAC_FOREIGN_VPN_DEFAULT=0` /
    `"foreign_default":"direct"` возвращают прежний DIRECT.

WinINET/WinHTTP используют `FindProxyForURLEx` (та же логика, но без SOCKS5-токенов).

## Маршруты и слоты

- **Основной слот** — SOCKS5 `127.0.0.1:1370` (WARP/MASQUE; при VLESS-профиле его держит nova-xray).
- **Вторичный слот** — HTTP `127.0.0.1:1371` (Opera), либо Tor `1375/1378`, либо импортированный
  профиль `1379/1380` (SOCKS5/HTTP).
- **RU-маршрут**: primary (если жив) → secondary (если жив) → `last_resort`.
- **EU-маршрут**: primary только если его измеренный выход **за рубежом**; всегда secondary;
  хвост `last_resort` (чтобы не отдавать гео-сайтам российский адрес).
- **YouTube-маршрут**: если primary выходит за рубеж — primary-first, иначе secondary-first;
  с Tor вторичным — primary-first (видео через Tor нецелесообразно).
- **`last_resort`** = `DIRECT` (по умолчанию) или `SOCKS5 127.0.0.1:1` при
  `NOVA_PAC_KILLSWITCH=1` (сознательный «kill switch»).
- **Telegram**: при явно выбранном warp/opera — pinned egress (без подмены на соседний слот и без
  DIRECT-хвоста); в auto при живом релее — `SOCKS5/PROXY 127.0.0.1:1372` + прежняя цепочка.

## Списки (`list/`, `ip/`)

| Файл | Смысл |
|---|---|
| `main.txt` | RU-список: сайты, блокируемые DPI (не гео) → туннель |
| `second.txt` | EU-список: гео-ограничения → зарубежный выход |
| `exclude.txt` | всегда DIRECT (CDN, банки и т.п.) |
| `ai.txt` | AI-сервисы (взаимодействует с DNS-разблокировщиком/NRPT) |
| `cloudflare.txt` | Cloudflare-домены; `ip/cloudflare.txt` — CIDR для fallback |
| `youtube.txt`, `telegram.txt`, `whatsapp.txt`, `discord.txt`, `games.txt` | профильные списки |
| `u_main.txt`, `u_second.txt`, `user_direct` | пользовательские списки (могут отсутствовать) |
| `rkn.txt` | панель проб для проверки стратегий (не маршрут) |
| `general.txt` | большой агрегированный список для проверок/winws-хостлистов (не PAC-маршрут) |

Обновление: `resources/nova_list_sync.py::sync_from_network` — `manifest.json` + sha256 из
`confeden/nova_updates/nova_pc` через зеркала (raw.githack, raw.githubusercontent, jsdelivr)
и прокси; в установленной сборке выполняется при старте (list_sync_worker).

## Ключевые env-переменные

| Переменная | Действие |
|---|---|
| `NOVA_PAC_KILLSWITCH=1` | при падении VPN не пускать напрямую (blackhole `SOCKS5 127.0.0.1:1`) |
| `NOVA_PAC_FOREIGN_VPN_DEFAULT=1` | **наш патч**: весь не-.ru трафик без совпадений — через VPN |
| `NOVA_ROUTING_BACKEND=auto\|current\|public-hybrid\|windivert-hybrid` | выбор транспорта |
| `NOVA_SYNC_WINHTTP_PROXY=1/0` | синхронизация WinHTTP с 1371 |
| `NOVA_DNS_UNBLOCK`, `NOVA_NRPT_*` | DNS-разблокировщик/NRPT-правила |
| `NOVA_WFP_ENABLE*`, `NOVA_WINDIVERT_*` | перехват приложений (WFP/Divert) |
| `NOVA_OPERA_FAKE_SNI`, `NOVA_OPERA_*` | Opera-слот: SNI-подстановка, релеи |
| `NOVA_WARP_*` (порт, сервис, ранний старт) | управление WARP/MASQUE |
| `NOVA_AUTOTUNE`, `NOVA_SAFE_FILTER_MODE` | режимы обучения стратегий |

Полный список — `grep -o "NOVA_[A-Z0-9_]*" nova.pyw | sort -u` (46 переменных в 1.43.2).

## Локальные модификации PAC (не из upstream)

1. Правило `*.ru → DIRECT` вставлено после явных пользовательских списков/режимов приложений
   и до AI-веток — чтобы явный выбор владельца оставался сильнее.
2. `foreign_default` (+ env `NOVA_PAC_FOREIGN_VPN_DEFAULT`) — выключатель «весь остальной
   трафик через VPN»; по умолчанию выключен (DIRECT + winws).

При обновлении исходников из upstream эти правки нужно переприменить.

## Замеры (2026-10-18, эта машина)

Медиана 3 попыток, `curl time_total` (мс):

| Сайт | DIRECT | WARP 1370 | Opera 1371 |
|---|---|---|---|
| ya.ru | **167** | 808 | 611 |
| vk.com | **432** | 599 | 657 |
| gosuslugi.ru | **481** | 648 | 616 |
| ozon.ru | **167** | 460 | 661 |
| sberbank.ru | **257** | 279 | 639 |
| gstatic (206/204) | **268** | 462 | 515 |

Вывод: для `.ru` прямой путь в 1.5–4.8 раза быстрее туннелей — это и есть выигрыш
от правила `*.ru → DIRECT`. Для заблокированных зарубежных сайтов DIRECT даёт `000/403`
или таймауты — там нужны слоты VPN.

## Ручная проверка PAC

```powershell
$pac = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:1369/nova.pac | Select-Object -Expand Content
$pac -match 'host\.slice\(-3\) === "\.ru"'
curl.exe -s -o NUL -w "%{http_code}" --socks5-hostname 127.0.0.1:1370 https://www.gstatic.com/generate_204
curl.exe -s -o NUL -w "%{http_code}" --proxy http://127.0.0.1:1371 https://www.gstatic.com/generate_204
```
