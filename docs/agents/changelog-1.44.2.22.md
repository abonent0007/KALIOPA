# Changelog 1.44.2.22 — политика маршрутов Route Lab

Дата: 2026-11-04. Сборка: `KALIOPA 1.44.2.22`.

## Что сделано

- **PAC: скрытый Tor-fallback только в «Авто».** Если явно выбран
  `secondary=opera`, `tor` или `profile`, PAC больше не подменяет его на Tor
  при падении слота. Явный выбор остаётся явным.
- Добавлен `tools/route_policy_check.py`: сверяет живые
  `temp/routing_settings.json` + `temp/profile-selection.json` + PAC + порты с
  политикой:
  - PAC 1369: SOCKS5 1370, HTTP 1371, DIRECT;
  - `routes.telegram=warp`, `ai_apps=opera`, `browser=auto`;
  - `secondary.mode=opera`, `opera_region=US`;
  - Tor/VLESS порты 1375/1378/1379/1380 закрыты;
  - primary — один профиль из разрешённых групп (MASQUE / Proton / CF AWG /
    VLESS / Custom).
- Добавлены тесты `tests/test_route_policy.py` (10) и проверка исходника,
  что Tor-fallback обёрнут условием `SECONDARY_AUTO`.

## Live-проверка

```
settings: ...\temp\routing_settings.json
selection: ...\temp\profile-selection.json
policy OK: PAC 1370/1371/DIRECT, Telegram WARP, Tor/VLESS reserve
```

Текущая конфигурация уже соответствовала графу; менять `routing_settings.json`
не потребовалось. Primary — `MASQUE/Cloudflare MASQUE 2`; Opera — US
(`77.111.246.61`); Telegram закреплён на WARP; 1375/1378/1379/1380 закрыты.

## Сборка

- 218 тестов OK, `py_compile`, статанализ, импорт-скан — чисто.
- Установщик: `build/Inno/v1.44.2.22/NovaSetup.exe`
  (110 827 137 байт, SHA-256 `937D08D56AC2CF62D24E1248F8D12FB6EF7EF5FEDB90A09735F4FBD0FAA5EE4A`).
- Установлено: `KALIOPA 1.44.2.22`.

## Замечание по графу

`opera_edge` в графе подписан `77.111.247.19:443 · US`, но `.247.19` — это SE;
US-выход сейчас `77.111.246.61`. На работу программы это не влияет: регион
задаётся `opera_region=US`, а IP — подпись узла.
