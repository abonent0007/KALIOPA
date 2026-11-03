# Движок обхода DPI: что у нас и что нового upstream

Проверено 2026-10-27. Относится к `bin/winws.exe` и `strat/*.json`.

## Что стоит у нас

`bin/winws.exe` — zapret **v72.13** (PE-таймстамп 2026-07-21), вместе с ним
`WinDivert64.sys` и `cygwin1.dll` из того же бандла.

## Не обновлять вслепую

В `bol-van/zapret-win-bundle` `zapret-winws/winws.exe` — сборка **v72.12**
(PE-таймстамп 2026-03-12), то есть **старее** нашей, хотя сам репозиторий
обновлялся 2026-10-21. Скачивать «последний» `winws.exe` из бандла = откат
движка. Сравнивать версии нужно по PE-таймстампу, а не по дате коммита.

Набор опций у обеих сборок одинаковый (115 флагов), поведение стратегий не
меняется.

Сборка закреплена: `tests/test_winws_binary.py` сверяет sha256
`bin/winws.exe` с v72.13. 27.10.2026 файл незаметно оказался сборкой v72.12 из
бандла (тот же размер, без версии в ресурсах) — откат поймали только по хешу и
восстановили из `C:\lib\backup-nova\nova-main-agents-md-20261018-1707.zip`.

## zapret2 / winws2 — отдельный движок

`bol-van/zapret2` (релиз **v1.0.6**, 2026-10-21) — новое поколение: `nfqws2`
для Linux и **`winws2.exe`** (656 КБ) для Windows. Это не апгрейд `winws`, а
другой CLI:

```
winws2.exe --wf-tcp-out=80,443 \
  --lua-init=@lua\zapret-lib.lua --lua-init=@lua\zapret-antidpi.lua \
  --filter-tcp=443 --filter-l7=tls --payload=tls_client_hello \
  --lua-desync=fake:blob=fake_default_tls:tcp_md5:repeats=11 \
  --lua-desync=multidisorder:pos=midsld
```

Ключевые отличия: стратегии описываются на Lua (`--lua-desync`), есть
`--payload`, `--filter-l7`, `--out-range`, `--blob`, профили с именами,
`zapret-auto` (автовыбор и детект сбоев), детект **mtproto**, работа с UDP/ICMP.

Что это значит для Nova: наш Rust-движок обучения и `strat/*.json` генерируют
классические аргументы `winws`. Переход на `winws2` — это новый адаптер, новый
формат стратегий (Lua) и переобучение, а не замена файла. Делать отдельным
проектом, с `winws` как запасным движком.

Практический интерес `winws2`: `--filter-l7=mtproto` для Telegram-релея и
`zapret-auto` вместо нашего перебора стратегий.

## Обязательная проверка стратегий

`winws` падает на неизвестной опции, поэтому любая стратегия с опечаткой просто
не работает. В `strat/*.json` уже находились опции из `nfqws`
(`--dpi-desync-multisplit-threshold`, `--dpi-desync-multisplit-re-inject`) и
устаревшая `--dpi-desync-split-tls`. Тест `tests/test_strategy_flags.py`
сверяет все опции стратегий с белым списком, сверенным по `docs/readme.md`
zapret v72.13.

## Инвентарь бинарей и библиотек (2026-11-03)

| Компонент | Версия / дата | Статус |
|---|---|---|
| `bin/winws.exe` | **v72.13**, 21.07.2026, sha `A14BFF1D…` | актуален: `bol-van/zapret` latest = v72.13. В win-bundle лежит v72.12 (март) — не откатывать |
| `bin/zapret2/winws2.exe` | **v1.0.6** (win-bundle 27.10.2026), 656 384 Б, sha `BA4CECCD…` | вендорно для UDP-узла и `--filter-l7=mtproto`; в рантайме не используется. `tests/test_zapret2_bundle.py` подтверждает `mtproto_initial`/`--filter-l7`; запуск требует администратора |
| `bin/nova-xray.exe` | xray-core **26.10.31** (31.10.2026), sha `958F31DE…` | обновлён 03.11.2026; исходник `Nova Android/tools/xray-core` — сток 26.10.31, локальных патчей нет. `go build ./...` и `go test ./...` в `nova-xray` проходят |
| `bin/nova-go.exe` | quic-go **v0.65.0**, usque **v4.2.1**, sha `A030D1B4…` | обновлён 03.11.2026; `go test ./...` проходит. Локальный `connect-ip-go` пропатчен под новый `HTTPStream() (*Stream, error)`; go-socks5 0.1.4, x/net 0.62.0, x/sys 0.49.0, x/crypto 0.58.0, wireguard 2026-05-22 |
| `bin/wireproxy-awg.exe` | **1.0.18** (Go 1.27), sha `0CE6EEAB…` | upstream `artem-russkikh/wireproxy-awg`; `--version` 1.0.18-dev, `--configtest` на живом AWG-профиле — Config OK |
| `bin/warp-plus` (в `nova-go`) | **v1.2.6 + Nova-патч** | upstream `bepass-org/warp-plus`; патч `tools/patches/warp-plus-nova-v1.2.6.patch` (динамические local address в netstack + info-лог); `go build ./...` OK |
| `bin/opera-proxy.windows-amd64.exe` | **v1.31.0** (22.10.2026), sha `9290DCC8…` | upstream `Alexey71/opera-proxy`; обновлён 03.11.2026. Флаги `-fake-SNI`, `-override-proxy-address`, `-api-proxy` сохранены. Лента `AS` (`77.111.245.12`) не используется: SurfEasy API отвечает 801, endpoint мёртв |
| `bin/tor/*` | Tor Expert Bundle **16.0** (tor 0.4.9.15, lyrebird 0.9.0), sha `1607D98F…` | обновлён 03.11.2026; sha256 совпал с `sha256sums-signed-build.txt`; `nova-tor --verify-config` — valid |
| Python-зависимости | requests 2.34.2, urllib3 2.8.0, certifi 2026.10.23, httpx 0.28.1, Pillow 13.0.0, pystray 0.19.5, cryptography 50.0.2 | обновлены в Python 3.14 (`uv pip install --upgrade`), входят в exe через PyInstaller |

Проверка после обновления: `203` теста, `py_compile`, `tools/static_analysis.py`,
`tools/import_scan.py`, `go test ./...` в `nova-go` и `nova-xray`,
`cargo check --workspace`.


