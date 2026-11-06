# Changelog 1.44.2.25 — порядок WARP по пингу и работоспособности

Дата: 2026-11-06. Сборка: `KALIOPA 1.44.2.25`.

- `nova_profiles._generated_metrics` читает `rtt_ms`, `fail_streak`, `ok` и
  `last_ok_at` из `profile-stats.json`; `warp-generated-state.json` с
  placeholder `999` больше не задаёт порядок.
- `_cloudflare_segments` сортирует: failures → известный рабочий (`ok >= 2`)
  → RTT → имя. Узел с пингом 28 мс и `fail_streak=1` уходит в хвост.
- `nova_profiles_ui` сортирует строки `AWG Cloudflare`: живой → рабочие →
  непроверенные → сбои, внутри по пингу; заголовок «рабочие → пинг».
- `build_attempt_plan` передаёт статистику в выбор Cloudflare-профилей.
- 3 новых теста; всего 282.
- Живой выбор: `WARPgen_15` (`162.159.192.1:4500`), до ~8 Мбит/с;
  `04/09/10/13/14` не подняли туннель, `01/02` рабочие.
