# test-backend — правила проекта

## Домен

Внутренняя **Django Admin** для подготовки тестов, назначения по отделам и просмотра результатов (оценка, время прохождения, статус). Параллельно — DRF API для внешних клиентов.

### Терминология

- **Отдел** — группировка пользователей; в UI «отдел», в коде `Group` или `Department` с M2M к пользователю. Выбери один подход, не дублируй два источника правды.
- **Тест** — сущность с вопросами/вариантами или ссылкой на конфиг; версионируй при необходимости.
- **Попытка / результат** — фиксация прохождения: пользователь, тест, `started_at`, `finished_at`, длительность, балл/процент, статус.

### Обязательные поля результата попытки

- Связь с пользователем и тестом
- `started_at`, `finished_at`
- Вычисляемая или сохраняемая **длительность**
- **Итог**: балл, процент, статус (`passed` / `failed` / `pending`)

---

## Django и Python

### Стек

- Django LTS или актуальная стабильная ветка; зависимости в `requirements.txt`.
- Приложение `testing` — бизнес-логика; `config/` — только настройки. Не смешивай бизнес-логику с `settings.py`.

### Модели

- `Meta`: `verbose_name`, `verbose_name_plural` на русском (договорённость команды).
- Внешние ключи с `on_delete` осознанно; для истории результатов `on_delete=PROTECT` на тест.
- Индексы на поля фильтрации: `started_at`, `user_id`, `test_id`.
- Код (имена классов, полей БД) — латиница, snake_case.

### Admin

- Регистрация через `@admin.register`.
- `list_display`, `list_filter`, `search_fields`, `date_hierarchy` — где уместно.
- `readonly_fields` для `duration`, `score` если считаются в `save()` или как property.
- `get_queryset` с `select_related` / `prefetch_related` для тяжёлых списков.
- Вычисляемые колонки через `@admin.display(description="...")`.
- Админка только для staff (`is_staff=True`).

### DRF API

- Вьюсеты и APIView в `api_views.py`; роутинг в `urls_api.py`.
- Сериализаторы в `serializers.py`; бизнес-логика в `services.py` — не в сериализаторах.
- Кастомные исключения в `api_exceptions.py`.
- Права доступа в `permissions.py`.
- `select_related` / `prefetch_related` в queryset вьюсетов.

### Безопасность

- Не храни секреты в репозитории.
- `DEBUG=False` в продакшене.
- Проверяй права доступа — `IsAuthenticated` как минимум для всех эндпоинтов.

### После изменений

```bash
python manage.py check
python manage.py test testing
```
