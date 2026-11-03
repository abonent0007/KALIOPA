# Changelog 1.44.2.21 — warp-plus, wireproxy, Tor; финальная сборка

Дата: 2026-11-03. Сборка: `KALIOPA 1.44.2.21`.

## Обновлено

| Модуль | Было | Стало | Проверка |
|---|---|---|---|
| warp-plus | f70ea7e + локальный патч | **v1.2.6 + Nova-патч** | `go build ./...`, `go test ./...` в `nova-go` — OK |
| wireproxy-awg | 1.0.13 | **1.0.18** (AmneziaWG v3) | `--version`, `--configtest` на живом AWG-профиле — Config OK |
| Tor Expert Bundle | 15.0.22 (tor 0.4.9.12) | **16.0 (tor 0.4.9.15**, lyrebird 0.9.0) | sha256 совпал с `sha256sums-signed-build.txt`; `--verify-config` — valid |

Патч warp-plus: `tools/patches/warp-plus-nova-v1.2.6.patch` — динамические
local address в netstack и info-уровень логов. Патч применён поверх v1.2.6,
`go build ./...` проходит.

## connect-ip-go: официальный источник проверен

`quic-go/connect-ip-go v0.7.0` уже собран под quic-go 0.65, но API не совпадает
с usque v4.2.1:

- официальный: `NewClientConn`, `ClientConn.Dial`, `ReadPacket`/`WritePacket`;
- usque: `DialH2`, `Dial`, `ReadPacketZeroCopy`/`WritePacketBuffer`.

Попытка перевести usque на официальный модуль дала ошибки сборки, поэтому
оставлен локальный снимок `Diniboy1123/connect-ip-go` + `HTTPStream`-патч.
Это осознанный pin, а не «забытое обновление».

## Rust

`cargo update` предлагает 21 обновление, но `link.exe` отсутствует. Установка
VS Build Tools через winget требует UAC и не завершилась; `Cargo.lock` возвращён
к проверенному состоянию. Rust остаётся единственным заблокированным пунктом.

## Сборка и проверки

- **203 теста OK** (добавлены 5 тестов версий транспортных бинарников).
- `go test ./...` в `nova-go`/`nova-xray` — OK; `py_compile`, статанализ,
  импорт-скан — чисто.
- Живьём: KALIOPA 1.44.2.21, MASQUE поднялся, Opera EU `.247.19`, Gemini и
  YouTube, порты 1370/1371/1372, `502` = 0. ChatGPT на момент финальной проверки
  (23:45 MSK) отвечал `Unable to load site` — внешнее ограничение OpenAI; ранее
  в этот же день он открывался через тот же выход.
- Установщик: `build/Inno/v1.44.2.21/NovaSetup.exe`
  (110 820 681 байт, SHA-256 `1553E8C6034C575B628FE4B08FE8159412735C1F7710BCC346E7529E79988C49`).
