# Master-аудит Nova — 2026-10-18

## Область и карта

- Точка входа: `nova.pyw` (GUI, PAC, оркестрация, управление помощниками).
- Модули: `resources/nova_*.py`, `tgrelay/`, `NovaDivert/`, `NovaWFP/`.
- Rust: `nova-rs` (обучение, пробы, TLS/JA4, zapret-IR).
- Go: `nova-go` (MASQUE/WARP), `nova-xray` (VLESS).
- Сборка: `Inno.py` → PyInstaller onedir → Inno Setup 6.
- Тесты: Rust workspace + `nova-tls --features shape`; Python-юнит-тестов нет,
  проверка — `python -m py_compile`.

## Baseline

`baseline.json` фиксирует старое поведение запущенной сборки до перезапуска и
post-build снимок нового staging-билда.

## Находки

| ID | Файл | Строка | Категория | Severity | Суть | Решение | Статус |
|---|---|---:|---|---|---|---|---|
| HARD-001 | `NovaWFP/README.md` | 73, 117–119 | HARDCODE | P2 | Захардкожены dev-пути `D:\Desktop\nova\temp\...` | Заменено на `<app>\temp\...` | FIXED |
| HARD-002 | `nova-go/go.mod` | 6 | HARDCODE | P3 | В комментарии путь `D:/Documents/Coding/Nova PC` | Заменено на `<repo>` | FIXED |
| HARD-003 | `Inno.py` | 895, 906, 911, 1439–1441 | HARDCODE | P3 | Кандидаты путей LLVM/NASM/CMake | Сначала env/PATH, кандидаты — fallback | ACCEPTED |
| HARD-004 | `resources/nova_list_sync.py`, `list_publish.py` | 302, 307; 31 | HARDCODE | P3 | Стоковые URL `confeden/nova_updates` | Не менять по политике форка; `list_publish` не запускать | ACCEPTED |
| HARD-005 | `nova.pyw` | 1369–1380 | HARDCODE | P3 | Фиксированные порты | Архитектурное решение, менять нельзя | ACCEPTED |
| GAP-001 | `Inno.py` | 253–258 | LOGIC_GAP | P1 | `safe_rmtree` молча глотал ошибки (`ignore_errors=True`) | Логирование ошибки без изменения поведения | FIXED |
| GAP-002 | `Inno.py` | 263–269 | LOGIC_GAP | P1 | Повторная сборка падала на существующем staging | `copytree(..., dirs_exist_ok=True)` | FIXED |
| GAP-003 | `Inno.py` | 1624–1634 | LOGIC_GAP | P1 | Clean build падал без `routing_settings.json` | Нейтральный файл с `version`/`opera_region` | FIXED |
| GAP-004 | `nova.pyw` | 1055, 1076 | LOGIC_GAP | P2 | Дубликат обработчика `--cleanup-old-exe` после backport | Дубликат удалён | FIXED |
| GAP-005 | `nova.pyw` | 8961, 9170 | LOGIC_GAP | P1 | В старой запущенной сборке не было `*.ru` и fallback был `DIRECT` | Новый build содержит `.ru` и VPN-fallback; live-проверено | FIXED |
| GAP-006 | `Inno.py` / `list_publish.py` | 1656–1674; 120–156 | LOGIC_GAP | P1 | Полная сборка пытается publish в `confeden/nova_updates` | `NOVA_SKIP_LIST_SYNC=1` + документировано | MITIGATED |
| GAP-007 | `Inno.py` | build_nova_xray | LOGIC_GAP | P2 | `WinError 5` на temp `nova-xray.exe` | `NOVA_SKIP_NOVA_XRAY=1`; использован валидный бинарник | MITIGATED |
| GAP-008 | runtime | 1371 | LOGIC_GAP | P2 | Вторичный слот иногда отвечает `000` | `tools/check_nova.ps1`; мониторить | OPEN |
| GAP-009 | `nova.pyw` | 1058–1074 | LOGIC_GAP | P3 | Защитный `except: pass` в cleanup | Оставлен как defensive | ACCEPTED |
| GAP-010 | проект | — | LOGIC_GAP | P2 | Нет Python-линетра/типчекера/юнит-тестов | Зафиксировано как coverage gap | OPEN |

## Предположения и пробелы покрытия

- `[ASSUMPTION]` Старая запущенная сборка — стоковая/предыдущая, а новый staging —
  форк с локальными изменениями.
- `[COVERAGE GAP]` Нет команд линтера/типчекера в `AGENTS.md`; Python проверяется только
  `py_compile` и живыми прогонами.
- `[COVERAGE GAP]` Нет Python-юнит-тестов для PAC/маршрутизации.
- `[COVERAGE GAP]` Новые seed-стратегии обфускации не измерены живыми пробами.
- `[COVERAGE GAP]` PAC проверен по правилу и финальному маршруту, не по полной матрице доменов.

## Верификация

- `python -m py_compile nova.pyw Inno.py` — PASS.
- `cargo test --workspace` — 750 passed, 0 failed, 1 ignored.
- `cargo test -p nova-tls --features shape` — 41 passed, 0 failed, 1 ignored.
- `go build ./...` в `nova-go` и `nova-xray` — PASS.
- Android `assembleGithubDebug` — PASS, APK 53.3 МБ.
- Полная PC-сборка — PASS: installer 102 МБ, staging `Nova.exe` 22:14:26.
- Live нового build: PAC 31 483 байта, `*.ru direct rule: OK`, финальный маршрут
  `SOCKS5 127.0.0.1:1370; PROXY 127.0.0.1:1371`; порты 1369/1370/1371/1372/1374 open;
  1370/1371 gstatic 204; direct `ya.ru` 302; direct `google.com` 204.
- Baseline vs post-build: 6 сценариев, 4 совпали, 2 изменения намеренные
  (`*.ru` и fallback VPN/прокси).

## Изменения

- `e18ca80` — surfacing cleanup failures, удаление hardcoded dev-путей.
- `bc55cc4` — `.ru`/VPN-маршрутизация и seed-стратегии.
- `bc2744c`, `1d21b22` — security backport и удаление дубликата.
- `ceff04a`, `c678b50` — устойчивость сборки, `NOVA_KEEP_STAGING`.
- `3fb80c3`, `68341bb`, `b3997c9` — списки, документация, аудит/скрипт проверки.

## Остаток

1. Живые замеры новых seed-стратегий; оставить выигрышные.
2. Проверить стабильность 1371 и fallback при падении VPN.
3. Добавить Python-тесты PAC/маршрутизации и линтер/типчекер.
4. Ревью остальных upstream-веток (perf/errors).
