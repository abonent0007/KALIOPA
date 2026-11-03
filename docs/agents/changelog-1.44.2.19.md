# Changelog 1.44.2.19 — транспортные модули и проверка обновлений

Дата: 2026-11-03. Сборка: `KALIOPA 1.44.2.19`.

## Обновления транспорта

| Модуль | Было | Стало | Проверка |
|---|---|---|---|
| `nova-xray` / Xray-core | 26.7.28 | **26.10.31** | `go test ./...` в `nova-xray`; `nova-xray version` |
| `nova-go` / quic-go | 0.61.0 | **0.65.0** | `go test ./...` в `nova-go`; MASQUE-профиль поднялся |
| `connect-ip-go` | старый API | локальный патч `HTTPStream() (*Stream, error)` | `tools/patches/connect-ip-go-httpstream.patch` |
| `opera-proxy` | 1.30.0 | **1.31.0** | EU `.247.19` → 204; ChatGPT в headed Chrome |
| `winws2` | 1.0.6 | без изменений | тест подтверждает `--filter-l7`/`mtproto_initial` |

Xray-core обновлён стоковым архивом тега в `Nova Android/tools/xray-core`
(локальных патчей не было). quic-go 0.65 потребовал правки `connect-ip-go`:
`HTTPStreamer.HTTPStream` теперь возвращает `(*Stream, error)`.

`opera-proxy` v1.31.0 сохранил нужные флаги (`-fake-SNI`,
`-override-proxy-address`, `-api-proxy`). Регион AS не подключён: SurfEasy API
отвечает `801`, endpoint `77.111.245.12` мёртв; рабочий регион — EU.

## Проверка обновлений в каждой сессии

- `docs/agents/module-updates.md` — источники, текущие версии, процедура и
  машинный блок `module-sources`.
- `tools/check_module_updates.py` — GitHub releases/tags + PyPI, кэш 12 ч,
  `--force`, `--quiet`, `--json`, `--fail-on-update`.
- `AGENTS.md`: при старте каждой сессии и после compaction — прочитать MD и
  запустить `python tools/check_module_updates.py --quiet`; не обновлять
  автоматически без backup/тестов.
- На 2026-11-03 найдено 5 pending: `go-socks5 0.1.4`, `urllib3 2.8.0`,
  `certifi 2026.10.23`, `Pillow 13.0.0`, `cryptography 50.0.2`.

## Сборка и проверки

- Тесты: **198 OK** (было 190), включая 7 новых на манифест/версии/статусы.
- `go test ./...`: `nova-go` и `nova-xray` — OK.
- `py_compile`, `tools/static_analysis.py`, `tools/import_scan.py` — чисто.
- Установлено: `KALIOPA 1.44.2.19`, окно 967×540, порты 1370/1371/1372,
  ChatGPT/Gemini через Opera EU, `502` = 0.
- Установщик: `build/Inno/v1.44.2.19/NovaSetup.exe`
  (109 514 572 байт, SHA-256 `59C3457770ECD04F016BB5A47E3ED9DF5932AFE734BCBEB84D356EF373F02CEC`).
