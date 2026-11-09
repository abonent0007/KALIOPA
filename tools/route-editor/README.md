# KALIOPA Route Lab

Визуальный редактор цепочки пакетов KALIOPA: узлы, связи, порядок, транспорт,
порты и итоговая JSON-конфигурация для переноса в приложение.

## Шаблон по умолчанию

При открытии сразу загружается **`templates/kaliopa-clean.json`** — текущая
цепочка KALIOPA 1.44.2.41 на 24 узла и 33 связи: PAC 1369, WARP/MASQUE 1370,
Opera EU 1371, Telegram 1372 → WARP, DNS/NRPT и резервы Tor / VLESS /
Proton AWG / CF AWG. Кнопка **«Шаблон Kaliopa»** перезагружает его после правок.
Та же схема лежит в программе — `resources/nova_route_spec.json`; равенство
файлов держит `tests/test_route_spec.py`.

Чтобы изменить шаблон для всех новых открытий — отредактируй
`templates/kaliopa-clean.json` (это обычный JSON Route Lab) и перезагрузи страницу.

## Запуск

Двойной клик по **`start-route-lab.bat`** в корне репозитория — сервер
запускается на `http://127.0.0.1:8099/`. Остановка — **Ctrl+C** в окне сервера.
Если окно потерялось, запусти `stop-route-lab.bat`.

Если PHP не установлен, `start-route-lab.bat` один раз скачает официальный
portable PHP 8.4 в `%LOCALAPPDATA%\KaliopaRouteLab\php` (или запусти
`tools\route-editor\setup-php.bat` вручную).

Альтернатива без батника:

```powershell
php -S 127.0.0.1:8099 -t tools\route-editor
```

Открыть `http://127.0.0.1:8099/`. Нужен PHP 8.0+ (проверено на 8.4).
Если PHP нет, страницу можно открыть как обычный HTML после сборки, но
сохранение на сервер будет недоступно — останется скачивание JSON.

## Снимок текущей конфигурации

`python tools/route-editor/snapshot.py` читает **установленную** Nova (выбор
профиля, `routing_settings.json`, живой `temp/nova.pac`, exit-страны слотов
1370/1371) и обновляет `templates/kaliopa-clean.json`: следующий запуск Route
Lab открывает актуальную цепочку, а не прошлый снимок. Без сети обновляется
всё, кроме подписей exit (остаются прежними). Тот же JSON записывается в
`resources/nova_route_spec.json` — схему, с которой Nova сверяет настройки и
PAC при каждой генерации (только журнал, маршруты не меняются).

## Как пользоваться

- **Палитра** слева: клик добавляет узел.
- **Связь:** клик по синему порту `out` справа, затем по зелёному `in` слева.
  `Esc` отменяет.
- **Перетаскивание:** тяни узел за заголовок.
- **Инспектор справа:** имя, тип, host/port, заметка; для связи — транспорт,
  условие (RU/EU/ai_apps), порядок и стиль линии.
- **Пресеты:** текущая схема KALIOPA, браузер через Opera, Telegram-релей,
  VLESS, пустая.
- **Низ:** JSON, текстовый маршрут и готовый промпт для агента. Кнопки
  «Копировать» и «Скачать .json».
- **Сохранить JSON** — POST в `routes/<name>.json`; список сохранённых —
  в выпадающем меню. Удаление — кнопка `⌫`.

## Схема JSON

```json
{
  "schema": "kaliopa.route-lab/1",
  "version": 1,
  "name": "KALIOPA current route",
  "notes": "что изменить",
  "nodes": [
    {"id":"device","type":"device","label":"Это устройство","sub":"Windows","x":60,"y":390,"host":"","port":"","note":"","tags":[]}
  ],
  "edges": [
    {"id":"e1","from":"device","to":"pac","transport":"локальный процесс","condition":"","label":"","order":1,"style":"solid"}
  ]
}
```

`style`: `solid` — основной путь, `reserve` — резерв, `dns` — служебный.
`condition` — селектор PAC/приложения (`RU`, `EU`, `ai_apps`, `telegram`).
`type`: `device`, `app`, `pac`, `proxy`, `relay`, `tls`, `dns`, `edge`, `server`.

## Передача конфигурации агенту

Вкладка **«Для агента»** содержит JSON в готовом виде:

> Ниже конфигурация цепочки KALIOPA из Route Lab. Нужно внести её в программу,
> не ломая текущую логику.

Скопируй этот блок и пришли в чат — по нему можно менять
`resources/nova_vpn_slots.py`, `resources/nova_transport_plans.py`, PAC и
watchdog'и.

## PHP API

`index.php` принимает:

- `GET ?action=list` — список `routes/*.json`;
- `GET ?action=load&file=name.json` — содержимое;
- `POST ?action=save` — JSON тела, атомарная запись;
- `POST ?action=delete&file=name.json` — удаление.

Данные лежат только локально в `routes/` и не коммитятся.
