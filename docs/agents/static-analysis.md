# Статический анализ и инвентарь статических данных

В окружении нет `ruff`/`flake8`/`mypy`, поэтому роль линтера выполняет
`tools/static_analysis.py` (только стандартная библиотека).

```powershell
python tools/static_analysis.py            # resources/ tgrelay/ tools/ tests/
python tools/static_analysis.py nova.pyw   # отдельный файл
python tools/static_analysis.py --json     # машинный вывод
```

Код возврата 0 — чисто, 1 — есть находки (годится для CI).

## Что проверяется

| Проверка | Правило |
|---|---|
| `unused_imports` | имя импортировано и ни разу не использовано; `__future__` и реэкспорты `__init__.py` игнорируются |
| `static_values` | строковые URL, IPv4-литералы, абсолютные Windows-пути, числа 1024–65535 (порты, таймауты, лимиты; степени двойки отброшены как размеры буферов) |
| `unguarded_calls` | `requests.*`, `urllib.request.*`, `socket.create_connection` вне `try` — **внешние данные** |
| `unguarded_setup` | `requests.Session`, `socket.socket`, `subprocess.*`, `ctypes.windll` вне `try` — создание ресурсов, справочно |

Guard считается и на уровне вызывающего: если функция или класс вызывается
внутри `try`, её внутренние вызовы помечаются обработанными.

## Инвентарь на 2026-10-28

`resources/`, `tgrelay/`, `tools/`, `tests/`: 25 URL, 165 IP, 2 абсолютных пути,
107 числовых констант. Разбор по происхождению:

- **Стоковые адреса инфраструктуры** (релеи, зеркала списков, DNS-каскад,
  NRPT-провайдеры) — не менять: правило форка «источники остаются стоковыми».
- **Порты архитектуры** (`1369`–`1380`, `17870`) продублированы в `nova.pyw`,
  `tgrelay/*`, `resources/nova_public_relays.py`. Это одна связная схема:
  менять их точечно нельзя, только целиком и с PAC.
- **Уже динамические**: TTL DNS-кэша (`NOVA_DNS_CACHE_TTL`), локальные TLD
  (`NOVA_LOCAL_DIRECT_TLDS`), режим Telegram-релея (`NOVA_TELEGRAM_RELAY`),
  авторотация профиля (`NOVA_PROFILE_ROTATION`) — читаются из env с дефолтом.
- **Данные внешних API** (адреса проб `nova_ai_region`) — статические по
  смыслу: это контракт с провайдерами, а не конфиг.

Новые литералы в этих категориях добавлять не нужно: URL — в `list/*.txt`
или env, числа — в именованную константу модуля.

## Что было исправлено этим прогоном

- `tgrelay/transparent_relay.py`: убраны два неиспользуемых импорта
  (`CFPROXY_DEFAULT_DOMAINS`, `start_cfproxy_domain_refresh`).
- `tests/test_fork_metadata.py`: убран неиспользуемый `import re`.
- `resources/nova_win_routes.py`: `list_adapters()` больше не падает, если
  `iphlpapi` недоступен или структура не совпала — возвращает `[]`.
- `resources/nova_tor.py`: `_connect_public()` пробует следующее семейство
  адресов, если `socket.socket()` на первом бросил `OSError`.
- `tgrelay/udp_transport.py`: `Socks5UdpEndpoint` закрывает сокеты, если
  создание или SOCKS5-associate сорвались (раньше оставался висеть control-сокет).
- `resources/nova_public_relays.py`: три копии `try/except` заменены одним
  `_safe_call()`, поведение снимка сохранено.
