# Сборка и запуск Nova (для агентов)

## Предусловия

| Что | Зачем | Проверка |
|---|---|---|
| Python 3.14 (полный, с Lib) | сборка PyInstaller; рантайм хелперов | `"$env:LOCALAPPDATA\Programs\Python\Python314\python.exe" --version` |
| PyInstaller 6.19+ | сборка exe | `python -c "import PyInstaller; print(PyInstaller.__version__)"` |
| pywebview, pythonnet, pystray, pillow | hidden-imports окна CAPTCHA/трея | импорт в том же интерпретаторе |
| Rust 1.90+ (cargo) | nova-rs (движок, TLS-терминатор) | `cargo --version` |
| Go 1.26+ и репозиторий `Nova Android` рядом | nova-go/nova-xray (replace в go.mod) | `go version`; `..\Nova Android\` |
| Inno Setup 6 (ISCC) | установщик (не обязателен для staging) | `ISCC.exe` в Program Files |
| `bin/` | winws, WinDivert, opera-proxy, warp, tor, помощники | `bin\winws.exe` |
| `profiles/` | пул AWG, ключ релея | `require_profile_sources` |
| `icon.ico` | иконка exe/трея | см. ниже |

В upstream отсутствуют `bin/`, `icon.ico`, ключи. Локально берутся из установки.

## Быстрый staging-билд (без Go и установщика)

```powershell
$env:NOVA_SKIP_NOVA_GO="1"; $env:NOVA_SKIP_NOVA_XRAY="1"
$env:NOVA_SKIP_NOVA_ENGINE="1"; $env:NOVA_SKIP_TLS_TERMINATOR="1"
$env:NOVA_SKIP_LIST_SYNC="1"
& "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe" "C:\Users\User\Documents\Nova-main\Inno.py"
```

Результат: `C:\Users\User\Documents\build\Inno\v<version>\Nova\` — готовая запускаемая папка
(`Nova.exe`, `resources\` c pyruntime, `bin\`, `list/ip/strat`, `profiles/`, `temp/`).
Промежуточные файлы PyInstaller: `C:\Users\User\Documents\build\temp_inno\dist|work`.
Если ISCC не найден, Inno.py печатает WARN и оставляет staging — это штатный режим.

## Полный установщик

`py Inno.py` (или python 3.14) при наличии Go, сестринского `Nova Android`, `bin/`, `profiles/`, ISCC.
Шаги: `require_paths` → sync списков (можно пропустить `NOVA_SKIP_LIST_SYNC=1`) →
`build_pyinstaller_dist` → staging профилей по белому списку → builtin-копии списков →
копирование python-рантайма для хелперов → рендер `NovaInstaller.generated.iss` → ISCC.

В личном форке перед полной сборкой обязателен `NOVA_SKIP_LIST_SYNC=1`: иначе `Inno.py`
вызывает `list_publish.publish_lists`, который коммитит и пушит списки в
`confeden/nova_updates`.

## Известные грабли

1. **PyInstaller 6.19 + Python 3.14:** `distutils` в `--exclude-module` вызывает
   `ValueError: Target module "distutils" already imported as ExcludedModule('distutils')`.
   В `Inno.py` `distutils` удалён из `PYI_EXCLUDED_MODULES` (локальный фикс). Если upstream
   обновит файл — переприменить.
2. **Нет `icon.ico` upstream.** Извлечь из установленного exe:
   ```powershell
   Add-Type -AssemblyName System.Drawing
   $i=[System.Drawing.Icon]::ExtractAssociatedIcon("C:\Users\User\AppData\Local\Nova\Nova.exe")
   $f=[System.IO.File]::Create("<repo>\icon.ico"); $i.Save($f); $f.Close()
   ```
3. **Нет `bin/`.** Копировать из установки: `AppData\Local\Nova\resources\bin` → `<repo>\bin`.
   Для Tor имена обязательны: `nova-tor.exe`, `nova-lyrebird.exe` (в `bin\tor`).
4. **Профили:** скопировать группы из `AppData\Local\Nova\profiles` (AWG Proton, AWG Cloudflare,
   Custom, MASQUE, VLESS) — `require_profile_sources` проверяет файлы, `stage_profiles` фильтрует.
5. **Tcl/Tk на 3.14:** Inno.py копирует `tcl_data`/`tk_data`; при сбоях задать `TCL_LIBRARY`/`TK_LIBRARY`.
6. **webview.platforms.android** — нефатальный warning при `--collect-all=webview`.
7. **Синк списков** требует `list_publish` + доступ к `confeden/nova_updates`; для сборки без сети —
   `NOVA_SKIP_LIST_SYNC=1`.
8. **`NOVA_SKIP_NOVA_ENGINE=1`** означает «движок не попадёт в сборку» (не «возьмёт старый»):
   в staging нужен уже готовый `bin\nova-engine.exe`; для установщика это окно работает иначе.

## Проверка staging

1. Файлы: `Nova.exe`, `resources\bin\winws.exe`, `list\main.txt`, `profiles\`.
2. Закрыть установленную Nova (через трей!), запустить staging `Nova.exe`.
3. PAC: `http://127.0.0.1:1369/nova.pac` — проверить наличие ожидаемых правил
   (`host.slice(-3) === ".ru"` для локального патча).
4. Каналы: `curl` через 1370 и 1371 → 204; прямой `.ru` быстрее туннеля.
5. Логи: `<staging>\temp\`.

## Замена установленной копии (по желанию)

1. Бэкап: `Compress-Archive AppData\Local\Nova` → `C:\lib\backup-nova\install-<ts>.zip`.
2. Закрыть Nova через трей (не убивать).
3. Скопировать staging поверх `AppData\Local\Nova` (или запускать staging как портативную).
4. Запустить, проверить PAC/порты; при проблемах — откат из zip.

## Тесты

- `python -m py_compile nova.pyw`
- `cargo test` в `nova-rs` (workspace); фазовая таблица:
  `NOVA_UPDATE_PHASE_TABLE=1 cargo test -p nova-probe --test table`
- Живые проверки после изменений: PAC, 1370/1371, `.ru` direct, логи `temp\`.
