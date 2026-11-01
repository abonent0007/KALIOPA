# Changelog 1.44.2.15 — динамическая личность релея

Дата: 2026-11-01. Заменяет зашитую `API_RELAY_KEY_VERSION = "1.43.2"`.

## Причина

Релей проверяет Basic-логин `nova-pc-<version>` вместе с ключом
`profiles/opera_relay.key`. Версия в логине должна быть той, под которую выпущен
ключ; продуктовый `CURRENT_VERSION` (1.44.2) даёт **407 Proxy Authentication
Required**. Проверено вживую через WARP:

| Логин | Ключ | Ответ релея |
|---|---|---|
| `nova-pc-1.43.2` | старый локальный | 404 от api2 (auth прошёл) |
| `nova-pc-1.44.2` | старый локальный | 407 |
| `nova-pc-1.44.1` | ключ из upstream 1.44.2 | 404 (auth прошёл) |
| `nova-pc-1.44.2` | ключ из upstream 1.44.2 | 407 |

То есть upstream-версия и версия ключа могут расходиться; жёсткая привязка к
любой из них одинаково опасна.

## Что сделано

- `resources/nova_relay_identity.py`:
  - читает ключ из `profiles/opera_relay.key` (fallback `awg/`);
  - берёт версии из `nova_updates/version.json` и `releases.atom` upstream;
  - пробует кандидатов через WARP (`127.0.0.1:1370`), различает `ok` / `407` /
    `unreachable`;
  - кэширует принятую версию в `temp/relay_identity.json` (с SHA-256 ключа) и
    `profiles/opera_relay.version`;
  - фоновая проверка после старта повторяется, пока WARP не поднимется;
  - `NOVA_RELAY_KEY_VERSION` — ручной override.
- `nova.pyw`: `api_relay_user()` вызывает `current_version()`; константа и её
  комментарий удалены. Продуктовый `CURRENT_VERSION` в логине больше не участвует.
- Ключ обновлён на upstream-ключ из публичного установщика 1.44.2 (принимает
  1.44.1). Старый ключ 1.43.2 сохранён в `C:\lib\backup-nova`.
- `AGENTS.md`: пункт «Relay identity pinned» заменён на «Relay identity dynamic».

## Живая проверка

```
15:36:53 [Relay] версия не проверена: пути к relay нет; остаюсь на 1.44.1.
15:37:26 [Relay] ключ принят для версии 1.44.1 (upstream: 1.44.2).
```

`temp/relay_identity.json`: `version=1.44.1`, `verified=true`,
`key_sha256=326753caa23aa914`. Порты 1370/1371/1372 открыты, `502` = 0,
Opera/ChatGPT работают как раньше.

## Тесты

`tests/test_relay_identity.py` переписан: проверяет отсутствие константы в
`nova.pyw`, приоритет env > кэш > маркер > default, инвалидацию кэша при смене
ключа, выбор первой принятой версии и поведение при недоступном релее.

Итог: **184 теста OK**, `py_compile` PASS, импорт-скан missing=0, статанализ
0 неиспользуемых импортов и 0 незащищённых вызовов данных.
