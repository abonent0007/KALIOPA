# Upstream profile-update watch

Личный форк не проверяет обновления самой программы на GitHub: `UPDATE_URL` в
`resources/nova_metadata.py` пуст, кнопка обновления скрыта, фоновый updater сразу
выходит. Из сети остаются только штатные обновления списков и профилей
(`nova_list_sync`, `nova_proton`, `nova_subscriptions`, `nova_issuance`).

## Версия форка

Версия сборки — `1.43.2.N` в `resources/nova_metadata.py`. Перед новой сборкой:

```powershell
python tools/bump_fork_version.py
```

Скрипт увеличивает последний компонент (`1.43.2.1` → `1.43.2.2`). Версия попадает
в `CURRENT_VERSION`, installer и Go/Rust-бинарники через `Inno.py`.

## Если обновление профилей сломалось или сменился сервер

Сначала проверь, что изменилось в upstream **в коде обновления профилей**, а не
включай автообновление программы:

```powershell
powershell -ExecutionPolicy Bypass -File tools/check_upstream_profile_updates.ps1
powershell -ExecutionPolicy Bypass -File tools/check_upstream_profile_updates.ps1 -Diff
```

Скрипт делает `git fetch upstream` и показывает diff только по:

- `resources/nova_list_sync.py`
- `resources/nova_proton.py`
- `resources/nova_subscriptions.py`
- `resources/nova_issuance.py`
- `resources/nova_profiles.py`
- `resources/nova_vless.py`
- `list_publish.py`
- `profiles/`

Изменения переносятся вручную и только если они относятся к обновлению профилей.
Адреса стоковых источников не меняются; `list_publish.py` не запускается — он
публикует списки в `confeden/nova_updates`.
