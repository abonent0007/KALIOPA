# Changelog 1.44.2.36 — Opera US через WARP, лента не из России

Дата: 2026-11-08. Сборка: `KALIOPA 1.44.2.36`.

## Причина «Gemini не нравится регион»

- WARP-выход основного слота — **RU** (`loc=RU`, `colo=ARN`). Gemini на таком
  выходе ругается на регион.
- Вторичный слот (Opera) не поднимался: `opera.log` — `discover API returned
  801`/таймауты, код 12, порт 1371 закрыт.
- Лента `opera_endpoints.json` (адреса, «собранные снаружи России») скачивалась
  **напрямую из России**, где raw.githubusercontent.com заблокирован: Python
  `urllib` всегда возвращал `{}`, менеджер падал в мёртвый EU-пул.
- Машина состояний давала **WARP-транспорт только для EU**. Выбранный US (AM)
  при отказе direct уходил в бесконечный `desired-am-retry` без WARP, хотя тот
  же `-country AM` через `-proxy socks5h://127.0.0.1:1370` отдаёт 200.

## Исправлено

- `nova_opera_feed.fetch_endpoint_feed`: прямое соединение, затем через живой
  слот (WARP SOCKS 1370, Opera HTTP 1371) — минимальный SOCKS5+TLS GET, без
  сторонних клиентов. Лента теперь реально грузится (замер: 3.2 с).
- `nova_opera_failover`: US/AM получает WARP-транспорт наравне с EU
  (`desired-am-over-warp`), плюс алиас `US → AM` в нормализации. Direct US
  больше не перезапускается вечно.
- `nova.pyw`: журнал называет новый переход.
- Тесты: `tests/test_opera_failover.py` (4 кейса: US-over-WARP, US без WARP,
  EU-over-WARP, сброс счётчиков).

## Живой замер

- `-country AM` **через WARP** → `HTTP 200`, выход не RU (проверено trace).
- `-country EU` через WARP → `loc=NL`, `colo=AMS`, 200.
- Прямой AM: TCP открывается, но туннель молчит — отсюда и нужен WARP-диал.

Всего тестов: **339** (+4).
