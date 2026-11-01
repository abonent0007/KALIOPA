# Proton и VLESS: что сломано, что починено

Две независимые ветки. VLESS **не** требует Proton: `nova_vless.py` → `bin/nova-xray.exe`,
`nova_proton.py` → `bin/wireproxy-awg.exe`. Перекрёстных импортов между модулями нет.

## Proton

Источник правды — upstream `v1.44`: два коммита, перенесённые дословно.

| Место | Было | Стало |
|---|---|---|
| `resources/nova_proton.py` | `android-vpn@5.4.44.0` / `ProtonVPN/5.4.44.0` | `android-vpn@5.20.21.0` / `ProtonVPN/5.20.21.0` (старая версия → 422/5003) |
| `resources/nova_captcha_window.py` | окно капчи без прокси наследовало системный PAC | `--proxy-server=direct://` при `proxy=None` (иначе ответ уходит другим IP → 12087) |

Кольцо дополнительного VPN (`resources/nova_vpn_slots.py`, `nova.pyw`): `Opera → AWG Proton → Tor`.
Proton-шаг пропускается, если профилей Proton нет (`_ring()`), а если группа не повезла трафик за
`PROFILE_AUTO_FAIL_SEC = 75` с, «Авто» идёт дальше. `OPERA_AUTO_FAIL_SEC` снижен 180 → 90 с.

Порядок стран Proton — по замеру задержки из России 2026-10-12:
`NL, NO, PL, RO, CA, MX, US, SG, JP, CH`.

Окно капчи открывается только в интерактивном запуске: кнопка «Перевыпустить» →
`issue_proton(interactive=True)` → `nova_captcha_window.solve()`. Автоматические обновления
профилей окно не показывают и на капче останавливаются.

## VLESS

`pcs` (`pinnedPeerCertSha256`) из ссылки больше не применяется по умолчанию: пин принадлежит
одному краю CDN, а `serverName` уже проверяется. Пример: узел `146.75.57.238` с
`sni=cdn.akamai.steamstatic.com` отдаёт сертификат `9B23…`, а ссылка пинит `CD6E…` — Xray отвечает
`peer cert is unrecognized (against pinnedPeerCertSha256)` и живой узел не поднимается.

Вернуть строгое поведение: `NOVA_VLESS_HONOR_PCS=1`.

## Проверка

```powershell
python -m unittest discover -s tests -p "test_*.py"        # 91 тест (2026-10-31)
python tools/static_analysis.py --quiet                     # 0 находок
```

Живая проверка Proton после перевыпуска: «Профили» → AWG Proton → проверка узлов, затем
`curl.exe -s --socks5-hostname 127.0.0.1:1370 https://2ip.io` — страна выхода должна совпадать с
выбранным узлом.

## Состояние на 2026-10-31 (живые проверки)

**Proton.** Перевыпуск проходит только через прокси: прямой `vpn-api.proton.me` отдаётся
DNS-подменой (NXDOMAIN) и режется по SNI (`Connection was reset`), а через Opera/Tor API отвечает
`400` (валидный ответ). Рукопожатие WireGuard при этом **не проходит вообще**: с закрытой Nova,
на чистом WG (без AmneziaWG-параметров), на портах 443/1194/1224 и для WARP-конфигов — ответа нет.
Значит сеть не пропускает WG-handshake; форк тут не при чём.

**VLESS.** Публичные узлы мёртвые: `a2.arshia-nova.ir` (Fastly) рвёт WebSocket
(`wsarecv: forcibly closed`), у 292 профилей в `profile-stats.json` ноль успешных подключений.
Плюс `pcs`-пин убивал часть живых узлов (снят по умолчанию).

**Opera.** Порт 1371 поднимается, но `CONNECT 77.111.246.61:443` не проходит (десятки проверок
подряд), edge Opera недоступен из этой сети; Opera US фактически выходил в NL (`loc=NL`).

**Рабочий путь.** Основной слот CF AWG/MASQUE (1370) открывает YouTube/Gemini/Instagram/X/LinkedIn
(200). ChatGPT отдаёт «Unable to load site» с IP `2a09:bac5:…` — это Cloudflare WARP, а OpenAI
блокирует WARP-диапазоны; не DNS и не форк.

