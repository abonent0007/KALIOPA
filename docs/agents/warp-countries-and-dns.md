# Страны выхода и DNS-маршруты (1.44.2.43)

## Выбор страны в генераторе AWG (только Custom AWG)

Каталог стран — `temp/warp-countries.json`, правится из «Профили → Custom AWG →
Настройки… → Страна выхода → Править…». Запись: `id`, `title`, `host`, `port`,
`iso`, `note`; без ключей и абсолютных путей. `id="any"` — «Любая», точку входа
ищет обычный сканер Cloudflare.

- Выбор страны подставляет её `host`/`port` в точку входа и переводит генератор
  в режим «Вручную»; «Любая» возвращает «Авто (скан)».
- После успешной проверки профиля генератор снимает выход туннеля
  (`http://ip-api.com/json` через временный SOCKS) и пишет `observed_ip`/
  `observed_loc` в `temp/warp-custom-meta.json` и в итог генерации.
- Свои серверы в каталоге — хозяина; для них в конфиге нужен их `PublicKey`
  пира, поэтому каталог лишь подставляет точку входа, а ключ остаётся от
  зарегистрированной личности Cloudflare.

Модули: `resources/nova_warp_countries.py`, `resources/nova_warp_custom_settings.py`
(`country`), `resources/nova_warp_generator.py` (`_socks5_exit_info`, `_probe_exit`,
`load_custom_meta`), UI — `CustomWarpSettings` и `WarpCountriesEditor`
(`resources/nova_profiles_ui.py`).

## Раздел «DNS» в окне «Профили»

Каталог резолверов — `resources/nova_dns_catalog.py`: публичные (Cloudflare,
Google, Quad9, dns-ai) и антиблок (malw, bezmezhau, geohide, geodema, mafioznik,
comss). Проверка — реальный UDP A-запрос через `nova_dns_probe.query`
(«✓ 39 мс» / «✗ нет ответа»), свой резолвер тоже проверяется.

Назначение хранится в `temp/dns-routes.json`: `default` + `routes` по доменным
группам PAC (`ru`, `eu`, `ai_apps`, `youtube`, `telegram`, `whatsapp`, `discord`,
`exclude`, `browser`). Применение — `setup_nrpt_dns_unblock` в `nova.pyw`:
выбранный резолвер подменяет каскад dns-ai → comss → geohide для имён своей
группы; незаданные группы остаются на каскаде. Имя относится к группе по
`_dns_namespace_route` (`*youtube*` → youtube, `*telegram*`/`*.t.me` → telegram,
`*whatsapp*`, `*discord*`, остальной набор NRPT — ai_apps).

Тесты: `tests/test_warp_countries.py`, `tests/test_dns_catalog.py`,
дополнения в `tests/test_warp_custom_settings.py`.

## Автоматизация и журнал изменений (1.44.2.45)

- **Страны определяются сами**: `nova_warp_generator.discover_countries` сканирует
  точки Cloudflare, поднимает каждый туннель и замеряет выход (`ip-api`), затем
  пишет каталог. При пустом каталоге в «Настройки…» запускается один раз за
  сеанс (кнопка «Найти страны…» — вручную в любой момент). Вводить хосты не нужно;
  «Править…» остался только для своих серверов.
- **DNS проверяется сам**: при входе на вкладку DNS выполняется «Проверить все»
  (один раз на состав каталога); назначения перечитываются с диска.
- Окно «Профили» при первом открытии сразу шире 900px.
- Адреса DNS резолверов резолвятся живым DNS-запросом, статический список —
   fallback (у заблокированных имён система молчит или отравлена).
- SOCKS5-рукопожатие вынесено в `_socks5_handshake` (было два копия в
  `_socks5_fetch_204` и `_socks5_exit_info`).
- **Удалённые заглушки:** действия `dns_test` из `ACTION_LABELS`/`_ACTION_METHODS`
  (осталось только `dns_test_all`); мёртвая ссылка `_on_dns_test_selected`.
- **Восстановленные звенья:** диспетчер действий больше не падает целиком при
  отсутствующем обработчике (таблица `_ACTION_METHODS`/`_ACTION_JOBS`), выбор
  `dns-ai.ru` для маршрута ведёт на локальный DoH `127.0.0.1`, выбор страны без
  хоста запрещён при сохранении.
