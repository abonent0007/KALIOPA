# Источники обновления модулей KALIOPA

Проверено: **2026-11-03**. Этот файл — единственный список того, откуда берутся
бинарники, Go-модули, Python- и Rust-зависимости, и как проверить, не вышла ли
новая версия.

## Правило каждой сессии

При старте новой сессии OpenCode и **после сжатия (compaction)**:

1. Прочитать этот файл.
2. Выполнить `python tools/check_module_updates.py --quiet`
   (кэш 12 часов; `--force` — свежая проверка).
3. Если есть обновления — сообщить пользователю списком и предложить план.
   **Не обновлять автоматически**: сначала backup, отдельная ветка/пункт плана,
   тесты, живая проверка, потом сборка.
4. Если проверка недоступна (нет сети/GitHub rate limit) — сказать об этом, не
   считать модули актуальными.

Скрипт читает машинный блок `module-sources` ниже. Меняя модуль, обновить здесь
`current`, дату и пройти процедуру из раздела «Порядок обновления».

## Таблица источников

| Модуль | Сейчас | Источник | Проверка | Обновление |
|---|---|---|---|---|
| Nova upstream | 1.44.2 | https://github.com/confeden/Nova | GitHub release | merge/rebase `upstream/main`, переприменить локальные патчи из AGENTS.md |
| zapret `winws.exe` | v72.13 | https://github.com/bol-van/zapret | GitHub release | скачать win-bundle, сравнить PE-таймстамп и sha256; **не откатывать** на v72.12; прогнать `tests/test_winws_binary.py`, `test_strategy_flags.py` |
| zapret2 `winws2.exe` | v1.0.6 | https://github.com/bol-van/zapret2 | GitHub release | заменить `bin/zapret2` целиком (exe + Lua + DLL), обновить хэши в `tests/test_zapret2_bundle.py` |
| Xray-core | 26.10.31 | https://github.com/XTLS/Xray-core | GitHub release | скачать stock-архив тега, заменить `Nova Android/tools/xray-core`, `cd nova-xray && go mod tidy && go test ./...`, собрать `bin/nova-xray.exe` |
| quic-go | 0.65.0 | https://github.com/quic-go/quic-go | GitHub release | `cd nova-go && go get github.com/quic-go/quic-go@vX && go mod tidy && go test ./...`; проверить патч `connect-ip-go` |
| uTLS | 1.8.2 | https://github.com/refraction-networking/utls | GitHub release | `go get github.com/refraction-networking/utls@vX`, пересобрать `nova-go`/`nova-xray`, живые TLS-пробы |
| go-socks5 | 0.1.0 | https://github.com/things-go/go-socks5 | GitHub tags | `go get github.com/things-go/go-socks5@vX`, `go test ./...` |
| usque (local fork) | d0eb96e | https://github.com/Diniboy1123/usque | git log/tags | обновить `Nova Android/build/deps/usque`, `go test ./...` в `nova-go`; проверить MASQUE |
| connect-ip-go (local + patch) | 66cba32 + HTTPStream patch | https://github.com/Diniboy1123/connect-ip-go | git log | синхронизировать `Nova Android/tools/connect-ip-go`; применить `tools/patches/connect-ip-go-httpstream.patch`; `go test ./...` |
| warp-plus (local fork) | local | https://github.com/bepass-org/warp-plus | git log | синхронизировать `Nova Android/tools/warp-plus`; `go test ./...`; проверить MASQUE/WARP |
| wireguard-go | 2025-05-21 | https://git.zx2c4.com/wireguard-go | git log | `go get golang.zx2c4.com/wireguard@<commit>`, пересобрать, проверить AWG |
| wireproxy-awg | 1.0.13-dev | AmneziaWG-форк (upstream `whyvl/wireproxy` несовместим) | вручную | пересобрать из форка, `wireproxy-awg --version`, живой AWG-профиль |
| opera-proxy | v1.31.0 | https://github.com/Alexey71/opera-proxy | GitHub release | скачать `opera-proxy.windows-amd64.exe`, backup старого, проверить флаги `-fake-SNI`, `-override-proxy-address`, `-api-proxy`; тест `.247.19` + ChatGPT |
| Tor Expert Bundle | 0.4.9.12 / 15.0.22 | https://dist.torproject.org/torbrowser/ | вручную | заменить `bin/tor`, `nova-tor.exe --version`, проверить webtunnel/obfs4 |
| Python-зависимости | requests 2.34.2, urllib3 2.7.0, certifi 2026.5.20, httpx 0.28.1, Pillow 12.2.0, pystray 0.19.5, cryptography 48.0.0 | PyPI | PyPI JSON API | обновить vendored-окружение/`resources`, `pip check`, полный pytest |
| Rust-крейты | workspace | crates.io | `cargo update --dry-run` / `cargo outdated` | обновить `Cargo.lock`, `cargo test --workspace`, `cargo check`; не менять `panic = "unwind"` |
| Opera endpoint feed | runtime | https://raw.githubusercontent.com/confeden/nova_updates/main/opera_endpoints.json | runtime fetch | ничего не собирать; проверить, что endpoint живой, иначе см. `docs/agents/chatgpt-opera.md` |

## Машинный список

```json module-sources
{
  "cache_hours": 12,
  "modules": [
    {"id": "nova-upstream", "name": "Nova upstream", "current": "1.44.2", "kind": "github-release", "repo": "confeden/Nova", "source": "https://github.com/confeden/Nova"},
    {"id": "winws", "name": "zapret winws", "current": "72.13", "kind": "github-release", "repo": "bol-van/zapret", "source": "https://github.com/bol-van/zapret"},
    {"id": "winws2", "name": "zapret2 winws2", "current": "1.0.6", "kind": "github-release", "repo": "bol-van/zapret2", "source": "https://github.com/bol-van/zapret2"},
    {"id": "xray-core", "name": "Xray-core", "current": "26.10.31", "kind": "github-release", "repo": "XTLS/Xray-core", "source": "https://github.com/XTLS/Xray-core"},
    {"id": "quic-go", "name": "quic-go", "current": "0.65.0", "kind": "github-release", "repo": "quic-go/quic-go", "source": "https://github.com/quic-go/quic-go"},
    {"id": "utls", "name": "uTLS", "current": "1.8.2", "kind": "github-release", "repo": "refraction-networking/utls", "source": "https://github.com/refraction-networking/utls"},
    {"id": "go-socks5", "name": "go-socks5", "current": "0.1.0", "kind": "github-tags", "repo": "things-go/go-socks5", "source": "https://github.com/things-go/go-socks5"},
    {"id": "usque", "name": "usque (local fork)", "current": "d0eb96e", "kind": "manual", "repo": "Diniboy1123/usque", "source": "https://github.com/Diniboy1123/usque"},
    {"id": "connect-ip-go", "name": "connect-ip-go (local + patch)", "current": "66cba32+patch", "kind": "manual", "repo": "Diniboy1123/connect-ip-go", "source": "https://github.com/Diniboy1123/connect-ip-go"},
    {"id": "warp-plus", "name": "warp-plus (local fork)", "current": "local", "kind": "manual", "repo": "bepass-org/warp-plus", "source": "https://github.com/bepass-org/warp-plus"},
    {"id": "wireguard-go", "name": "wireguard-go", "current": "2025-05-21", "kind": "manual", "source": "https://git.zx2c4.com/wireguard-go"},
    {"id": "wireproxy-awg", "name": "wireproxy-awg", "current": "1.0.13-dev", "kind": "manual", "source": "AmneziaWG fork; upstream whyvl/wireproxy incompatible"},
    {"id": "opera-proxy", "name": "opera-proxy", "current": "1.31.0", "kind": "github-release", "repo": "Alexey71/opera-proxy", "source": "https://github.com/Alexey71/opera-proxy"},
    {"id": "tor", "name": "Tor Expert Bundle", "current": "0.4.9.12/15.0.22", "kind": "manual", "source": "https://dist.torproject.org/torbrowser/"},
    {"id": "python", "name": "Python deps", "kind": "pypi", "packages": {"requests": "2.34.2", "urllib3": "2.7.0", "certifi": "2026.5.20", "httpx": "0.28.1", "Pillow": "12.2.0", "pystray": "0.19.5", "cryptography": "48.0.0"}},
    {"id": "rust", "name": "Rust crates", "kind": "manual", "check": "cargo update --dry-run"},
    {"id": "opera-feed", "name": "Opera endpoint feed", "current": "runtime", "kind": "manual", "source": "https://raw.githubusercontent.com/confeden/nova_updates/main/opera_endpoints.json"}
  ]
}
```

## Порядок обновления

1. **Backup**: `C:\lib\backup-nova\` (zip исходников/бинарников, которые меняем).
2. **Один модуль за раз**: обновить источник → `go mod tidy`/`pip`/замена бинаря.
3. **Тесты**: `python -m unittest discover -s tests -p "test_*.py"`,
   `tools/static_analysis.py`, `tools/import_scan.py`,
   `go test ./...` в `nova-go`/`nova-xray`, `cargo test --workspace` (если Rust).
4. **Живая проверка**: порты 1370/1371/1372, `204` через SOCKS/HTTP, ChatGPT в
   headed Chrome, `502` = 0.
5. **Версия и сборка**: `python tools/bump_fork_version.py`, `Inno.py`, overlay-install.
6. **Запись**: обновить `current` в этом файле, `docs/agents/engine-upgrades.md`,
   changelog; закоммитить.

## Особые случаи

- **`opera-proxy` AS**: лента `nova_updates` публикует `AS` (`77.111.245.12`), но
  SurfEasy API отвечает `801` на `-country AS`, endpoint мёртв. Не считать AS
  рабочим резервом; рабочий регион — EU.
- **`winws2`/mtproto**: движок поддерживает `--filter-l7=mtproto` (подтверждено
  `tests/test_zapret2_bundle.py`), но запуск требует администратора и отдельного
  WinDivert-фильтра; в рантайме не используется.
- **`connect-ip-go`**: локальный патч обязателен для quic-go ≥ 0.65; без него
  `nova-go` не собирается (`HTTPStream() (*Stream, error)`).
- **Xray-core**: локальных патчей нет, источник — стоковый архив тега; хранится
  в `Nova Android/tools/xray-core`, не в этом репозитории.
- **Секреты**: `profiles/opera_relay.key`, `tgrelay/cf_ws.key`, `bin/` и локальные
  профили не коммитить и не публиковать.
