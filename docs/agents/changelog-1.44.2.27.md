# Changelog 1.44.2.27 — прямые российские площадки

Дата: 2026-11-06. Сборка: `KALIOPA 1.44.2.27`.

- `list/exclude.txt`: добавлены `avito.com`, `wildberries.com`, `qiwi.com`,
  `yoomoney.com`, `yandex.com`, `mycdn.me`, `vk-cdn.net`, `sberbank.com`,
  `vtb.com`, `alfabank.com`, `rt.com`, `sputniknews.com`, `tass.com`.
- `list/u_direct.txt`: тот же набор для текущей установки.
- `Inno.py`: `u_direct.txt` нового установщика засевается публичными
  always-direct доменами; `tools/install_overlay.ps1` не перезаписывает
  пользовательские `u_*.txt`.
- PAC проверен: топовые `.ru` и добавленные `.com`/CDN возвращают `DIRECT`;
  официальные сервисы не идут через WARP/Opera.
- 286 тестов OK; policy OK; 1370/1371 живы.
