# Changelog 1.44.2.32 — DNS-AI через DoH

Дата: 2026-11-07. Сборка: `KALIOPA 1.44.2.32`.

- `nova-go/dnsdoh`: локальный DNS-слушатель (UDP+TCP) → DoH по HTTP/2; кэш 60 с,
  `SERVFAIL` при отказе, опциональный UDP-fallback, `--proxy http://|socks5://`,
  `--parent-pid`. Регистрация группы `dns` в `cmd/nova-go`.
- `resources/nova_dns_doh.py`: выбор слота (1370 → 1371 → напрямую), запуск с
  health-check, `query`, `supported_names` (сравнение с системным DNS),
  суточный кэш `temp/dns_doh_support.json`.
- `nova.pyw`: `setup_nrpt_dns_unblock` добирает имена через DoH, если UDP-каскад
  пуст; правила указывают на `127.0.0.1`; резолвер стартует/останавливается
  вместе с правилами; повтор при появлении туннеля.
- Причина: dns-ai.ru не имеет UDP/53 и требует HTTP/2; Windows без DoH-клиента
  не может ходить к нему через NRPT напрямую.
- Тесты: 328 Python (+13), Go `dnsdoh` (5).
