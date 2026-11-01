# Changelog 1.44.2.14 — целостность и чистка хардкодов

Дата: 2026-11-01. Область: служебные модули Nova и точки их вызова; поведение
маршрутизации, PAC и установленной сборки не менялось.

## Удалённые заглушки и дублирование

| Что удалено | Замена |
|---|---|
| Две копии запуска PowerShell в `nova_dns_adapters.py` и `nova_process_hygiene.py` | `resources/nova_win_ps.py`: `run()` + `json_rows()` |
| Две копии разбора `ConvertTo-Json` | `nova_win_ps.json_rows()` |
| Неверная фраза «дальше берём первый endpoint без замера» в `OperaProxyManager.note_exit_code` | Точное сообщение: следующий запуск повторит замер |
| `json`/`subprocess` в служебных модулях после выноса | Импорты удалены, статанализ 0 |

## Восстановленные логические звенья

1. **DoH не может «тихо не запуститься».** `DohResolver.start()` теперь ждёт
   фактический bind и поднимает `OSError`, если порт занят; `nova_doh_service.start()`
   в этом случае возвращает DNS адаптеров к снимку, а не переводит систему на
   несуществующий резолвер.
2. **Проба VLESS не блокирует обновление подписки.** `_probed_add_identities()`
   при любой ошибке пробы оставляет все новые узлы (fail-open), при отказе
   отдельных узлов — отсеивает только их.
3. **Proton-варианты не ломают выпуск.** Если `nova_proton_variants` отсутствует
   в сборке, `variant_files()` возвращает пустой список, а выпуск идёт как раньше.
4. **Счётчик вариантов** читается из `NOVA_PROTON_VARIANT_COUNT`, а не только из
   аргумента по умолчанию.
5. **Источник endpoint'ов Opera** расширяется `NOVA_OPERA_ENDPOINTS_URL`; зеркала
   остаются fallback'ом.
6. **Возраст уборки процессов** настраивается `NOVA_PROCESS_ORPHAN_AGE`.

## Инвентаризация статических данных

Проверено `tools/static_analysis.py`: 430 статических значений (URL/IP/пути/порты).
Заменены на настраиваемые там, где значение описывает среду, а не протокол:

- путь сборки в `install_overlay.ps1` → `$env:USERPROFILE`;
- порт DoH → `NOVA_DOH_PORT`;
- таймаут выбора Opera → `NOVA_OPERA_SELECTION_TIMEOUT`;
- проба VLESS → `NOVA_VLESS_PREFLIGHT_TIMEOUT`, `NOVA_VLESS_PREFLIGHT_WORKERS`;
- число Proton-конфигов → `NOVA_PROTON_VARIANT_COUNT`;
- источник Opera-ленты → `NOVA_OPERA_ENDPOINTS_URL`;
- возраст уборки процессов → `NOVA_PROCESS_ORPHAN_AGE`.

Оставлены константами намеренно: `API_RELAY_KEY_VERSION=1.43.2` (ключ выпущен под
неё), порты 1369–1380, `DEFAULT_OPERA_FAKE_SNI`, протокольные строки.

## Проверки

| Проверка | Результат |
|---|---|
| `python -m unittest discover -s tests` | **177 OK** (было 160) |
| `py_compile` изменённых файлов | PASS |
| `tools/import_scan.py` (весь проект) | files=110, missing=0, optional_missing=0 |
| `tools/import_scan.py --diff` | files=12, missing=0 |
| `tools/static_analysis.py` | unused_imports=0, unguarded_calls=0, unguarded_setup=10 (запуск процессов, не данные) |

Новые тесты: `test_win_ps.py` (7), `test_subscription_preflight.py` (4),
`test_opera_feed.py` (3), `test_doh_resolver.py::test_start_reports_a_port_that_cannot_be_bound`,
`test_proton_variant_files.py` (+2).

## Что не менялось

- PAC, правила маршрутизации, слоты WARP/Opera/Tor, порты.
- Формат `routing_settings.json`, профили, подписки, список доменов.
- Версия relay-логина и брендинг OBNOVA.
