# Архитектура Nova (для агентов)

Версия 1.43.2. Верхнеуровневая карта; детали — ADR (`docs/adr/`) и исходники.

## Компоненты

| Компонент | Роль | Язык/формат |
|---|---|---|
| `nova.pyw` | GUI (tkinter), оркестратор, генерация PAC, управление помощниками | Python 3.14, ~33.5K строк |
| `resources/` | Модули приложения: маршрутизация, профили, списки, пробы, DNS-AI, TLS/Tor/VLESS | Python |
| `nova-rs/` | Движок: обучение стратегий (Томпсон), эволюция, классификация Cloudflare, фазы туннеля, TLS/JA4, терминатор | Rust 2024 |
| `nova-go/` | MASQUE/WARP клиент, SOCKS5 (порт 1370) | Go 1.26 |
| `nova-xray/` | VLESS-помощник (порт 1370 при VLESS-профиле) | Go 1.26 |
| `NovaDivert/` | Перехват трафика (WinDivert), hybrid redirect | C/Go helper + Python |
| `NovaWFP/` | Windows Filtering Platform: TCP/UDP редиректы приложений | Python-хелперы + WFP API |
| `tgrelay/` | Прозрачный Telegram-релей (MTProto через WS/CF) + фазовая классификация | Python |
| `strat/` | Сиды стратегий winws (JSON) | данные |
| `fake/` | Бинарные маски ClientHello/QUIC (в т.ч. kyber) | данные |
| `list/`, `ip/` | Доменные и IP-списки | данные |
| `profiles/` | Профили: AWG Proton, AWG Cloudflare, Custom, MASQUE, VLESS | данные |
| `bin/` | Сторонние бинарники (winws, WinDivert, opera-proxy, warp, tor, помощники) — в upstream отсутствует | бинарники |

## Поток данных (упрощённо)

```
Пользователь/браузер
   │  PAC (http://127.0.0.1:1369/nova.pac)
   ▼
Маршрут: DIRECT (winws-обход) │ SOCKS5 127.0.0.1:1370 (WARP/MASQUE/VLESS)
        │ PROXY 127.0.0.1:1371 (Opera) │ Tor 1375/1378 │ профиль 1379/1380
   ▼
Приложения с перехватом (NovaWFP/NovaDivert): Telegram/WhatsApp/Discord → свои релеи/редиректы
   ▼
Сеть провайдера (DPI) → сервер
```

- **Обход DPI** делает winws (zapret) на прямом пути: перехват пакетов через WinDivert,
  стратегии из `strat/*.json`.
- **Туннели** используются, когда нужен зарубежный выход (гео) или прямой путь не работает.
- **Обучение** (nova-rs) непрерывно оценивает стратегии; CUSUM фиксирует смену режима,
  Томпсон-сэмплинг выбирает кандидата; `winws --dry-run` отсеивает невалидные.

## Рантайм и состояние

- Один экземпляр приложения. Порты: 1369 PAC, 1370 primary SOCKS (WARP/MASQUE/VLESS),
  1371 secondary HTTP (Opera), 1372 TG-релей, 1374 TLS-терминатор, 1375/1378 Tor,
  1379/1380 импортированный профиль.
- Состояние/логи: `<app>\temp\` (`nova.pac`, `tls_terminator.log`, pid-файлы, кэши).
  Настройки маршрутизации: `routing_settings.json` (+ `temp/routing_settings.json`).
- Раскладка «ресурсов»: при установке `resources/` содержит Python-рантайм для хелперов
  (`pyruntime/`), пакеты (`webview`, `pythonnet`, `PIL`, `pystray`), WFP/NovaDivert-хелперы.

## Где искать логику (якоря)

- PAC и маршруты: `nova.pyw::generate_pac` (~L8461), шаблон `FindProxyForURL` (~L8954),
  `FindProxyForURLEx` для WinINET (~L9181).
- Решения транспорта приложений: `resources/nova_routing_backends.py` (WFP/windivert/relay/singbox).
- Цепочки TCP-попыток: `resources/nova_transport_plans.py` (warp-socks/opera-http/direct; pinned egress Telegram).
- Списки: `resources/nova_list_sync.py` (`sync_from_network`, `raw_url`, `mirror_urls`).
- Профили: `resources/nova_proton.py` (выпуск Proton), `nova_vless.py`, `nova_subscriptions.py`.
- Tor: `resources/nova_tor.py`; DNS-AI: `resources/nova_dns_ai.py`; Cloudflare: `nova_cloudflare_*`.
- TLS/SNI: `nova-rs/crates/nova-tls` (JA4, profiles chrome/firefox/yandex, терминатор),
  `docs/adr/0003-tunnel-phases.md`, `docs/adr/0004-neutral-sni.md`.
- Стратегии/маски: `strat/*.json`, `fake/*.bin`.

## Сборка и артефакты

- `Inno.py` — сборщик: staging через PyInstaller + упаковка Inno Setup 6. Детали — `build.md`.
- Rust-воркспейс собирается отдельно (`cargo build --release`), Go-помощники — `go build` (см. `build.md`).
- Установленная копия: `C:\Users\User\AppData\Local\Nova\` (exe + resources + списки + профили).

## Ограничения дизайна (важно для правок)

- Нельзя «просто перезапустить» установленный exe после правок исходников — нужна пересборка.
- `bin/` и ключи (`tgrelay/cf_ws.key`, `awg/opera_relay.key`) в upstream не входят.
- go.mod содержит `replace` на сестринский репозиторий `Nova Android` — без него Go-часть не собрать.
- Разделение списков (RU/ EU/ AI/ Cloudflare/ YouTube) — измеренное решение; менять только с замерами.
