# Changelog 1.44.2.20 — все проверяемые обновления модулей

Дата: 2026-11-03. Сборка: `KALIOPA 1.44.2.20`.

## Обновлено

| Модуль | Было | Стало |
|---|---|---|
| Python: requests | 2.32.3 | **2.34.2** |
| Python: urllib3 | 2.6.3 | **2.8.0** |
| Python: certifi | 2026.2.25 | **2026.10.23** |
| Python: httpx | 0.27.0 | **0.28.1** |
| Python: Pillow | 12.2.0 | **13.0.0** |
| Python: cryptography | 48.0.0 | **50.0.2** |
| Go: go-socks5 | 0.1.0 | **0.1.4** |
| Go: x/net | 0.57.0 | **0.62.0** |
| Go: x/sys | 0.47.0 | **0.49.0** |
| Go: x/crypto | 0.54.0 | **0.58.0** |
| Go: usque (local) | d0eb96e | **v4.2.1** (фикс `PROTOCOL_VIOLATION`) |
| Go: wireguard-go (transitive) | 2025-05-21 | **2026-05-22** |

Python-пакеты обновлены через `uv pip install --python Python314 --upgrade`
(штатный `pip` в Python 3.14 сломан: отсутствует `pip._vendor.cachecontrol.caches`).

### Адаптация под usque v4.2.1

- `masque/crypto.go`: `PrepareTlsConfig(..., false)` — новый аргумент `insecure`.
- `masque/register.go` и `masque/cfapi_test.go`: `HasErrorMessage` заменён на
  `HasErrorCode`/`ErrorsAsString`.
- `go test ./...` в `nova-go` — OK, MASQUE-профиль поднялся.

### Что не обновлено и почему

- **connect-ip-go 66cba32** — upstream перешёл на удалённый в quic-go 0.65
  `http3.ParseCapsule`; локальный снимок 2025-10 + `HTTPStream`-патч остаётся.
- **Rust-крейты** — `cargo update` предлагает 21 обновление, но проверить
  нельзя: в окружении нет `link.exe` (MSVC Build Tools). `Cargo.lock` возвращён
  к проверенному состоянию.
- **warp-plus** — локальные патчи Nova, upstream-версия несовместима; не трогали.
- **wireproxy-awg / Tor** — ручные источники, обновлений в этой сети нет.

## Проверки

- **198 тестов OK** под Python 3.14 (и под 3.11).
- `go test ./...` в `nova-go` — OK; `nova-xray` — OK.
- `py_compile`, `tools/static_analysis.py`, `tools/import_scan.py` — чисто.
- Живьём: KALIOPA 1.44.2.20, MASQUE через usque v4.2.1, Opera EU `.247.19`,
  ChatGPT и Gemini в headed Chrome, порты 1370/1371/1372, `502` = 0.
- Установщик: `build/Inno/v1.44.2.20/NovaSetup.exe`
  (109 831 780 байт, SHA-256 `3BC92BE2AE6148AE1D59F67985F73FE9B8CFED40155313D02FF06D2EA3B8246D`).

## Проверка обновлений

`python tools/check_module_updates.py --quiet` теперь не находит обновлений среди
проверяемых GitHub/PyPI-модулей. Rust и connect-ip-go отмечены как manual с
причинами выше.
