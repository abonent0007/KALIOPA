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

## Инвентарь бинарей и библиотек (2026-10-31)

| Компонент | Версия / дата | Статус |
|---|---|---|
| `bin/winws.exe` | **v72.13**, 21.07.2026, sha `A14BFF1D…` | актуален: `bol-van/zapret` latest = v72.13. В win-bundle лежит v72.12 (март) — не откатывать |
| `bin/zapret2/winws2.exe` | **v1.0.6** (win-bundle 27.10.2026), 656 384 Б, sha `BA4CECCD…` | добавлен вендорно для будущего UDP-узла; в рантайме не используется |
| `bin/zapret2/lua/*.lua` | lib 93 714, antidpi 51 866, auto 21 123, obfs 21 333 | закреплены тестом `tests/test_zapret2_bundle.py` |
| `bin/nova-xray.exe` | xray-core **26.7.28** (18.10.2026) | апстрим Xray v26.10.31 (31.10) — обновление требует сборки форка, исходников в репозитории нет |
| `bin/wireproxy-awg.exe` | 1.0.13-dev (13.04.2026) | это AmneziaWG-форк; upstream `whyvl/wireproxy` v1.1.3 несовместим (нет AWG) |
| `bin/opera-proxy.windows-amd64.exe` | v1.30.0 (06.10.2026) | репозиторий апстрима не найден (`yeltuk/opera-proxy` → 404), обновление невозможно |
| `bin/tor/*` | Tor Expert Bundle **15.0.22** (tor 0.4.9.12, lyrebird 0.8.1) | `dist.torproject.org` недоступен из этой сети (DNS), обновление отложено |
| Python-зависимости | requests 2.34.2, urllib3 2.7.0, certifi 2026.05.20 | вендорены в `resources/`, обновляются только пересборкой окружения |

Проверка после обновления: `98+` тестов, `py_compile`, `tools/static_analysis.py`,
`cargo check --workspace`.

