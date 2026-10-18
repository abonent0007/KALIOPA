# Аудит локального форка Nova — 2026-10-18

## Контекст

- PC-форк: `C:\Users\User\Documents\Nova-main`, ветка `personal`, upstream `confeden/Nova` (1.43.2).
- Android-форк: `C:\Users\User\Documents\Nova-Android-Fork`, ветка `personal`, версия 1.33.
- Сборка: `C:\Users\User\Documents\build`.
- Upstream `main` не ушёл вперёд: fork опережает его на локальные коммиты.

## Архитектура

- `nova.pyw` (~33.5 тыс. строк) — GUI, PAC, оркестрация, управление помощниками.
- `resources/nova_*.py` — транспорт, маршрутизация, профили, списки, DNS/AI, Tor/VLESS.
- `nova-rs` — Rust-ядро: обучение, пробы, TLS/JA4, zapret-IR, TG-релей.
- `nova-go` / `nova-xray` — Go-помощники: MASQUE/WARP и VLESS.
- Android: Kotlin/Gradle + `nova-core` (Go) + `nova-xray` (JNI).
- `Inno.py` — PyInstaller + Inno Setup 6, артефакты вне репозитория.

## Что изменено в этой сессии

1. **Маршрутизация.** `foreign_default` теперь по умолчанию VPN: весь не-.ru трафик без
   совпадений идёт через RU-маршрут (WARP/MASQUE/VLESS → резервные слоты).
   `*.ru → DIRECT` поднят выше явных режимов приложений; пользовательские списки остаются
   выше правила. Откат: `NOVA_PAC_FOREIGN_VPN_DEFAULT=0` или `"foreign_default":"direct"`.
2. **Обфускация/SNI.** В `strat/general.json` добавлены три seed-стратегии:
   `general_GOOG_RNDSNI`, `general_GOOG_SNIEXT`, `general_VK_KYBER`. Использованы маски
   Google TLS/QUIC, `sniext` и kyber-маска VK; по ADR 0002 Google-маска была успешнее
   yandex-маски (0.518 против 0.420), а kyber-маски ранее не входили в сиды.
3. **Безопасность.** Из upstream-ветки перенесён фикс command injection в self-deletion и
   admin relaunch: `--cleanup-old-exe`, `subprocess.list2cmdline`, без `shell=True`.
   Дубликат обработчика удалён.
4. **Сборка.** `Inno.py`: повторная сборка в существующий staging (`dirs_exist_ok=True`),
   нейтральный `routing_settings.json` при отсутствии источника, `NOVA_KEEP_STAGING=1`
   для портативной папки.
5. **Списки/доки.** Клиентская синхронизация из `nova_updates` выполнена: 12 файлов без
   изменений; из `general.txt` удалены 13 дублей AI-доменов. Исправлены устаревшие якоря
   и битая ссылка в `nova-rs/README.md`; зафиксировано, что `list_publish.py` в личном
   форке запускать нельзя (он пушит в `confeden/nova_updates`).

## Проверки

- `cargo test --workspace` — успешно.
- `cargo test -p nova-tls --features shape` — успешно (BoringSSL, libclang, NASM, CMake).
- `go build ./...` в `nova-go` и `nova-xray` — успешно.
- Android `assembleGithubDebug` — успешно; APK `Nova_1.33.apk` (53.3 МБ).
- Полная PC-сборка — успешно: установщик 102 МБ, портативный staging сохранён.
- Пересобраны `nova-tls-terminator.exe`, `nova-engine.exe`, `nova-go.exe`; `nova-xray.exe`
  использован из успешной сборки (повторная сборка упёрлась в WinError 5 на temp-файле).
- Старая сборка (до перезапуска): в её PAC нет правила `*.ru`, финальный маршрут
  `DIRECT`. Это подтверждено `tools/check_nova.ps1`:
  `*.ru direct rule: MISSING`, `return "DIRECT"`.
- Живые каналы старой сборки: 1370 → 204, 1371 → 204, direct `ya.ru` → 302,
  direct `google.com` → 204.
- Новый staging-билд (`Nova.exe` 22:14:26) запущен и проверен: PAC 31 483 байта,
  `*.ru direct rule: OK`, финальный маршрут `SOCKS5 127.0.0.1:1370; PROXY 127.0.0.1:1371`;
  порты 1369/1370/1371/1372/1374 открыты, 1370/1371 → 204.

## Слабые места

1. Монолит `nova.pyw`: высокое связывание, глобальное состояние, риск регрессий.
2. Нет Python-юнит-тестов; проверка — `py_compile` и живые прогоны.
3. Обфускация: 36 seed-стратегий `general` были привязаны к yandex-маске; новые сиды
   требуют живых замеров, иначе выигрыш не доказан.
4. Маршрутизация: смена `foreign_default` на VPN увеличивает нагрузку/задержку и зависит
   от живости слотов; нужен мониторинг fallback/killswitch.
5. Сборка: `list_publish` — publish-шаг, а не клиентская синхронизация; в личном форке
   обязателен `NOVA_SKIP_LIST_SYNC=1`.
6. `nova-xray` может блокироваться на temp-файле при повторной сборке; безопасный обход —
   `NOVA_SKIP_NOVA_XRAY=1` при уже собранном бинарнике.
7. Локальные `profiles/` содержат ключи/аккаунты; они исключены из git, но остаются на диске.
8. Вторичный слот 1371 нестабилен: в одном замере был `000`, затем `204`.
9. Документация местами отстаёт от кода (якоря, счётчики, планы).
10. В upstream есть незамерженные ветки (security/perf/errors); security-фикс взят, остальные
    требуют отдельного ревью.

## AGI-консультации

- По ошибке `Author identity unknown` рекомендован `git -c user.name=... -c user.email=...`.
  Для личного форка выбран более безопасный путь: `NOVA_SKIP_LIST_SYNC=1`, чтобы не выполнять
  publish в `confeden/nova_updates`.
- По `WinError 5` на `nova-xray.exe` в Temp: вероятная блокировка файла/антивирус; безопасно
  использовать уже собранный бинарник, если исходники не менялись. Так и сделано.

## Что осталось

1. Снять живые метрики новых seed-стратегий и оставить только выигрышные.
2. Проверить стабильность 1371 и fallback при падении VPN.
3. Добавить Python-тесты PAC/маршрутизации и линтер/типчекер.
4. Решить судьбу остальных upstream-веток (perf/errors) после отдельного ревью.
