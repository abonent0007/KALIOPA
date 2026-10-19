# План: динамическая ротация узлов профиля при деградации

## Цель

Когда текущий узел выбранной группы (Proton/VLESS/Custom/MASQUE) устойчиво деградировал,
переключиться на более быстрый существующий узел той же группы. Сервер выдачи профилей
не трогаем: никаких новых запросов, регистраций и подписок. Только уже лежащие профили.

## Решения

- **v1 — RTT/ошибки, без синтетического throughput-теста.** AGI-консультация (Google AI
  Mode) рекомендовала не качать 128 КБ каждые 30 с: ложные срабатывания, лишний трафик,
  буферизация Windows. В v1 — маленький canary-запрос через активный SOCKS5 (~200 байт)
  для проверки живости туннеля + direct RTT до узлов для выбора кандидата.
- Порог: 3 последовательных деградированных сэмпла, cooldown 15 минут, не более 2
  переключений в час, минимальное время на узле 90 с.
- Кандидат должен быть не менее чем на 30% лучше по direct RTT; узлы с недавним fail
  исключаются.
- Явный `MODE_PROFILE` не трогаем. При `MODE_AUTO` ротация только для Proton; для
  VLESS/Custom — только при явно выбранной группе.
- Группа и страна выбора сохраняются: кандидаты фильтруются по group/country.
- Переключение — через существующий `apply_selection_now()`; выбранный узел пишется в
  preferred-профиль, чтобы план группы начинал с него, но оставался fallback на другие узлы.
- Всё выключается `NOVA_PROFILE_ROTATION=0`.

## Задачи

### Task 1: чистая политика и тесты
- [ ] `resources/nova_profile_rotation.py`: `RotationPolicy`, `ProfileCandidate`,
  `RotationDecision`, `choose_candidate`.
- [ ] `tests/test_profile_rotation.py`: baseline, 3 сэмпла, cooldown, лимит 2/час,
  порог 30%, fail-узлы, явный profile, EWMA, reset.
- Acceptance: `python -m unittest discover -s tests` зелёный; модуль не делает сети.

### Task 2: адаптеры профилей и здоровья
- [ ] `load_candidates`: records + stats, свежий RTT, при необходимости `nova_latency`.
- [ ] `probe_canary`: `nova_exit_probe.fetch_via_proxy` через SOCKS5, бюджет 4 с.
- [ ] `measure_direct`: RTT текущего узла из stats или TCP-проба.
- Acceptance: чистые функции тестируются с фейками; сетевые адаптеры не падают при
  недоступном узле.

### Task 3: монитор и интеграция
- [ ] `ProfileRotationMonitor`: поток 45 с, проверка state/connected/starting/recovering,
  сброс политики при смене active_id, защита от повторного переключения.
- [ ] `WarpManager`: `_profile_rotation_state`, `_rotate_to_profile`, запуск монитора,
  `NOVA_PROFILE_ROTATION`.
- Acceptance: explicit profile не переключается; auto — только Proton; нет серверных
  вызовов; переключение идёт через `apply_selection_now`.

### Task 4: проверка
- [ ] `python -m py_compile nova.pyw resources/nova_profile_rotation.py`.
- [ ] `python -m unittest discover -s tests`.
- [ ] `cargo test --workspace` (регрессия не затронута).
- [ ] Сборка staging и live-проверка: подключиться, дождаться 3 сэмплов, проверить лог;
  принудительно снизить порог в тестовом окружении и убедиться, что переключение
  происходит один раз и не чаще cooldown.
- [ ] Проверить, что при `MODE_PROFILE` и `NOVA_PROFILE_ROTATION=0` переключений нет.

## Риски

| Риск | Митигация |
|---|---|
| RTT не равен throughput | v1 — health-сигнал; позже добавить пассивные счётчики байт/опциональный throughput-тест |
| Ложное переключение | 3 сэмпла, EWMA, 30% улучшение, 15 мин cooldown, 2/час |
| Гонка с ручным выбором | перед switch перечитать selection/active_id; `MODE_PROFILE` запрещён |
| Переключение при старте/восстановлении | проверять `_is_starting_now`/`_is_recovering_now` |
| Уход из выбранной страны | фильтр `country` для Proton |
| Лишний трафик | canary ~200 байт раз в 45 с; кандидаты — только после деградации |

## AGI-консультации

- Design review: Google AI Mode — v1 без 128 КБ throughput-зонда, только RTT/ошибки;
  учесть гонки с ручным выбором, cold-start EWMA, cooldown, Windows `perf_counter`.
- Перед реализацией: повторная консультация по коду (duck.ai/Google AI) на каждом слайсе.
