# zapret2 (winws2): что это и как применить в Nova

Проверено 2026-10-31.

## Версии

| Что | Версия / дата |
|---|---|
| `bol-van/zapret2` последний релиз | **v1.0.6**, 21.10.2026 (`zapret2-v1.0.6.zip`, tar.gz, openwrt) |
| Репозиторий zapret2 | обновлён 31.10.2026 (коммиты после релиза: `!` в hostlists, autolist, `udp2icmp` CGNAT) |
| `bol-van/zapret-win-bundle` | обновлён 27.10.2026: `winws.exe` 223 232 Б (v72.12), **`winws2.exe` 656 384 Б** |
| Lua-библиотеки в бандле | `zapret-lib.lua` 93 714, `zapret-antidpi.lua` 51 866, `zapret-auto.lua` 21 123, `zapret-obfs.lua` 21 333, `zapret-tests.lua`, `zapret-pcap.lua` |

Лицензия в корне zapret2 не указана (файла LICENSE/COPYING нет); перед встраиванием
кода — сверять с автором. Мы уже поставляем `winws.exe` из того же проекта.

## Чем winws2 отличается от нашего winws

`winws` (v72.x) принимает классические аргументы: `--dpi-desync=multisplit`,
`--dpi-desync-split-pos`, `--dpi-desync-fooling`, `--dpi-desync-fake-*`.

`winws2` — другой движок и другой CLI:

```
winws2.exe --wf-tcp-out=80,443 \
  --lua-init=@lua\zapret-lib.lua --lua-init=@lua\zapret-antidpi.lua \
  --filter-tcp=443 --filter-l7=tls --payload=tls_client_hello \
  --out-range=-d10 \
  --lua-desync=fake:blob=fake_default_tls:tcp_md5:repeats=11 \
  --lua-desync=multidisorder:pos=midsld
```

Что даёт:

- стратегии описываются на Lua (`--lua-desync`), а не флагами;
- фильтры `--filter-l7` (tls, http, quic, **mtproto**, wireguard, stun, discord) и `--payload`
  (`tls_client_hello`, `quic_initial`, `wireguard_initiation`, `mtproto_initial`);
- `--blob` — именованные маски, `--out-range`, профили с именами, таймеры, conntrack-позиции;
- `zapret-auto` — оркестратор: сам определяет сбои и переключает стратегии;
- `zapret-obfs` — `udp2icmp`, `ippxor`, `synhide` (обфускация на уровне протоколов);
- `blockcheck2` — автоподбор стратегий (генерирует готовый Lua-профиль).

## Как это можно применить

**1. Генератор стратегий (низкий риск, быстрый эффект).**
Запускать `blockcheck2` (Windows-версия в бандле) на тестовых доменах и переносить найденные
параметры в наши `strat/*.json` (перевод `multidisorder/pos` → `--dpi-desync=multidisorder`,
`--dpi-desync-split-pos`). Не меняет рантайм, даёт свежие рабочие комбинации для winws.

### Прогон blockcheck2 2026-10-31 (Windows, Git Bash)

Окружение: в бандле нет cygwin-curl, а Windows-curl не понимает `/dev/null` и `/tmp`
(`curl: (23)`), поэтому использован шим `shim/curl` (перевод путей) и патч `MINGW*|MSYS*` →
`CYGWIN*` в `blockcheck2.sh`. Домены: `bbc.com` (в этой сети `youtube.com` отдаётся DNS как
SERVFAIL, `rutracker.org` — NXDOMAIN).

Найденные рабочие комбинации для HTTP/80 (`curl_test_http`, AVAILABLE):

- `--payload=http_req --lua-desync=multidisorder:pos=midsld:seqovl=midsld-1`
- `--lua-desync=syndata --payload=http_req --lua-desync=multisplit`
- `--lua-desync=syndata --payload=http_req --lua-desync=multidisorder`
- `--payload=http_req --lua-desync=fake:blob=fake_default_http:ip_ttl=1:repeats=1`
- `--lua-desync=fake:blob=fake_default_http:tcp_md5:repeats=1 --lua-desync=fakedsplit:pos=method+2:tcp_md5`
- то же с `blob=0x00000000`
- `fake:blob=0x00000000:ip_autottl=-1,3-20:repeats=1` + `fakedsplit`

Оговорка: kill winws2 между итерациями под Git Bash не срабатывал («A copy of winws2 is already
running»), поэтому часть результатов могла быть завышена; к концу прогона WinDivert-служба
перестала открывать фильтр («service cannot be started»), и TLS-часть недостоверна. Для чистого
прогона нужен убийца процессов по PID изнутри скрипта (taskkill) и закрытая Nova.

Переносимые в наш winws идеи: `multidisorder:pos=midsld`, `pos=1,midsld`,
`multisplit:pos=sniext+1` (= `--dpi-desync-split-pos=sniext+1`), `seqovl`.
`wssize:wsize=1:scale=6` и `syndata` — только в winws2, аналога в winws нет.

### Кандидаты в strat (2026-10-31)

В `strat/general.json` добавлены три записи (всего 42), флаги проверены
`tests/test_strategy_flags.py`:

| Имя | Суть |
|---|---|
| `general_MD_midsld` | `multidisorder` + `split-pos=midsld`, fooling `badseq` |
| `general_MS_sniext1` | `multisplit` + `split-pos=sniext+1` (TLS, позиция после SNI) |
| `general_MD_seqovl` | `multidisorder` + `split-pos=midsld` + `split-seqovl=1` с маской `tls_clienthello_www_google_com.bin` |

Копия тут же положена в установленную `AppData\Local\Nova\strat\general.json`
(прежняя сохранена как `general.json.bak-*`). Проверка штатным «Advanced Strategy
Checker» Nova выполняется при старте: имена появятся в `nova_console.log`
вместе с оценкой, после чего видно, выигрывают ли они у текущих сидов.

### Запуск winws2: обязательные DLL рядом с exe

`winws2.exe` собран под Cygwin и грузит `cygwin1.dll`, а WinDivert ищет
`WinDivert.dll`/`WinDivert64.sys` рядом с исполняемым файлом. Без них:
«система не обнаружила cygwin1.dll» / «не обнаружила WinDivert.dll». Поэтому в
`bin/zapret2/` лежат `winws2.exe`, `cygwin1.dll`, `WinDivert.dll`,
`WinDivert64.sys`, `lua/*`, `windivert.filter/*` и пресеты.

Прототип UDP-узла (2026-10-31, сценарий `wg_proto.cmd`):
`--wf-raw-part=windivert.filter/windivert_part.wireguard.txt` +
`--filter-l7=wireguard --payload=wireguard_initiation` +
`--lua-desync=repeater:instances=2:repeats=3` +
`--lua-desync=luaexec:code="desync.rnd=brandom(math.random(32,64))"` +
`--lua-desync=fake:blob=rnd`. Требует остановленного winws (общий WinDivert),
поэтому проверяется только при закрытой Nova.

**Результат перебора (US-FREE-77, 2026-10-31):** четыре варианта — `repeater+fake:rnd`,
`fake:rnd:repeats=6`, `fake:0x00…:repeats=2`, `fake:rnd:ip_autottl=-1,3-20` — все
стартуют (`winws2 alive=True`), handshake уходит, **ответа нет** ни в одном.
Вывод: клиентские fake/repeater не пробивают блокировку WireGuard на этом пути;
для Proton нужен TCP-транспорт (Stealth/udp2raw) или не-WG выход (Opera/Tor/VLESS).
`winws2` остаётся в `bin/zapret2` для будущих QUIC/mtproto-экспериментов.

### mtproto-фильтр для Telegram: проверено, не применимо

Проверка прямого TCP до дата-центров Telegram (2026-10-31, без прокси):
`149.154.167.50:443`, `149.154.167.51:443`, `91.108.56.130:443`,
`149.154.175.50:443` — **все таймаут на connect** (5 с). Это блокировка по IP,
а не по сигнатуре MTProto: `--filter-l7=mtproto` модифицирует пакеты уже
установленного TCP-соединения и не может пробить недоступный адрес.
Поэтому Telegram остаётся на WSS-релее через разрешённые CDN-домены
(`kws2.*`), а mtproto-фильтр в Nova не включаем.






**2. Отдельный UDP-узел (средний риск).**
`winws2` умеет `--filter-l7=wireguard,stun,quic,discord` и `zapret-obfs` (`udp2icmp`,
`ippxor`). Это ровно то, чего `winws` не делает: обход DPI для **UDP** (WireGuard/QUIC).
Можно держать два процесса: `winws` для TCP и `winws2` для UDP на непересекающихся фильтрах
(`--wf-tcp` против `--wf-udp`). Ограничение: два WinDivert-хендла допустимы, но фильтры должны
быть разнесены по портам, иначе пакеты обработаются дважды.

**3. Замена TCP-движка на winws2 (высокий риск).**
Потребует: новый формат стратегий (Lua), адаптер в Rust-движке обучения (сейчас он генерирует
аргументы winws), переобучение, регрессию всех `strat/*.json`. Делать только после 1–2.

**4. Использовать как библиотеку.** Нельзя: `winws2` — самостоятельный C-бинарник без
публичного API; логика в Lua-файлах, которые он загружает через `--lua-init`. Интеграция —
только запуск процесса (как сейчас с `winws.exe`) или форк исходников.

## Рекомендация

Порядок: **(1) → (2) → при необходимости (3)**.
Сейчас в Nova стоит `winws` v72.13 (июль), это **новее** бандлового v72.12 — не откатывать.
`winws2` добавляет то, чего у нас нет в принципе: UDP/WireGuard-обход и mtproto-фильтр; для
Telegram-релея и для «Proton/WARP не соединяется» это наиболее релевантные возможности.
Первый практический шаг — прогнать `blockcheck2` и сравнить его набор с нашими сидами.
