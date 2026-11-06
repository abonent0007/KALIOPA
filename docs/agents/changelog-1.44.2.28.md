# Changelog 1.44.2.28 — генератор Custom WARP

Дата: 2026-11-06. Сборка: `KALIOPA 1.44.2.28`.

- `nova_warp_generator.generate_custom_one`: один AWG-профиль в
  `profiles/Custom`, локальная регистрация/identity, скан endpoint’ов,
  fallback, I1, DNS/MTU/keepalive.
- `build_warp_conf`: необязательные `dns`, `mtu`, `keepalive`; batch-вызов
  сохраняет прежние defaults.
- `nova_profiles_ui`: кнопка «Сгенерировать» в Custom AWG, отдельный handler.
- `nova.pyw`: `ProfileJobs.generate_custom` и `ProfilesUiContext.generate_custom`;
  после создания сохраняет `mode=profile` и вызывает `apply_selection_now`.
- 6 тестов: конфиг, defaults, один/два профиля, ручной endpoint, сохранность
  `WARPgen_*`; всего 292.
- Не используются сторонние API, отдающие private key.
