# Changelog 1.44.2.24 — подписки, Xray JSON и новые протоколы

Дата: 2026-11-06. Сборка: `KALIOPA 1.44.2.24`.

## Этап A

- `resources/nova_subscription_meta.py`: разбор `Subscription-Userinfo`,
  `Profile-Update-Interval`, `Profile-Title` (`base64:`), `Support-Url`,
  `Profile-Web-Page-Url`, `Announce` из заголовков и `#`-строк тела.
- `FetchResult` хранит заголовки; `refresh` обновляет метаданные и на 304.
- `nova_profiles_ui`: остаток трафика, срок, название провайдера, число
  пропущенных чужих ссылок.
- `nova_vless`: `eh` → `heartbeatPeriod` (uint32), `ech`/`cs` под env-флагами.
- `parse_xray_json`: импорт VLESS из `/subJsonPath` 3x-ui без inbound/routing.
- 35 новых тестов.

## Этап B

- `VlessNode` стал общим узлом Xray: `protocol` (`vless`, `vmess`, `trojan`,
  `shadowsocks`), пароли/методы, отдельная identity для не-VLESS.
- Разбор `trojan://`, `vmess://` (base64 JSON) и `ss://` (SIP002 + legacy).
- Сборка outbound для всех четырёх протоколов; VMess без `alterId`
  (ядро 26.x его больше не читает), Trojan без `flow` (удалён из ядра).
- `nova_profiles`: импорт из буфера/файла и листинг всех Xray-профилей;
  группа отображается как «Xray», папка/id остались `VLESS`.
- `nova-xray/registry`: зарегистрированы vmess/trojan/shadowsocks.
- JSON-подписки 3x-ui с Trojan/VMess/SS также импортируются.
- 22 новых теста, включая `nova-xray check`.
