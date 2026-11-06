# Changelog 1.44.2.30 — настройки генератора Custom WARP

Дата: 2026-11-06. Сборка: `KALIOPA 1.44.2.30`.

- `resources/nova_warp_custom_settings.py`: пресеты `optimal`/`fast`/`compat`
  и `custom`, нормализация (границы MTU/keepalive/портов, чистка DNS/SNI,
  «рваный» джанк → случайный), `resolve()` в аргументы генератора,
  `load`/`save` в `temp/warp-custom-settings.json`.
- `nova_profiles_ui.CustomWarpSettings`: окно настроек с пресетами-пилюлями,
  полями endpoint/DNS/MTU/keepalive/SNI/Jc-Jmin-Jmax, «Сбросить»/«Отмена»/
  «Сохранить»; правка поля переключает пресет на «Свой».
- Действие «Настройки…» в строке Custom AWG; ctx-методы
  `get_warp_custom_settings`/`save_warp_custom_settings`.
- `generate_custom_one`: `endpoint_attempts`/`sni_attempts` (1–3 и 1–4),
  пресет «Быстрый отклик» расширяет перебор точек входа.
- Тесты: 315 (16 новых в `tests/test_warp_custom_settings.py` и один на
  сужение циклов проверки).
