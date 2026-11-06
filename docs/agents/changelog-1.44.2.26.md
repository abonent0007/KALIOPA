# Changelog 1.44.2.26 — резервные списки, кэш UI и тёмная тема

Дата: 2026-11-06. Сборка: `KALIOPA 1.44.2.26`.

- `nova_subscriptions.DEFAULT_SOURCES`: добавлены `vpn-free-russia`
  `verified_configs.txt` и `ru_configs.txt`; `MAX_TOTAL_VLESS` 600 → 900.
- `nova_profiles_ui`: `_profile_tree_signature` + `_file_cache`; файлы
  профилей/статистика/подписки читаются только при изменении mtime/size.
- `nova.pyw`: тёмная палитра `SETTINGS_THEME` в стиле Windows 11
  (`#202020`, `#2B2B2B`, синий `#0067C0`, hover `#60CDFF`).
- `NovaTunnelGuard`: задача переведена на `wscript //B` + VBS + скрытый
  PowerShell; окно больше не появляется каждые 5 минут.
- 4 новых теста (кэш/резервные источники); всего 286.
