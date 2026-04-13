Проведи аудит безопасности проекта и выдай список проблем по приоритетам.

## Что проверять

### 1. Секреты в репозитории

Прочитай `config/settings.py` и `.env` (если есть). Проверь:
- `SECRET_KEY` не захардкожен в settings.py напрямую (должен браться из env).
- Пароли БД, API-ключи не в коде.
- `.env` есть в `.gitignore`.

Поищи паттерны в коде:
```bash
grep -rn "SECRET_KEY\s*=" config/ testing/ --include="*.py"
grep -rn "PASSWORD\s*=" config/ testing/ --include="*.py"
```

### 2. DEBUG и настройки продакшена

- `DEBUG = False` в проде (или берётся из env).
- `ALLOWED_HOSTS` не содержит `*` в проде.
- `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` для HTTPS.

Запусти: `python manage.py check --deploy`

### 3. Права доступа в API

Прочитай `testing/api_views.py`. Проверь каждый ViewSet/APIView:
- Есть `permission_classes` — минимум `[IsAuthenticated]`.
- Нет эндпоинтов без авторизации, кроме намеренно публичных.
- `DEFAULT_PERMISSION_CLASSES` в settings.py — что стоит по умолчанию?

### 4. Права в Admin

Прочитай `testing/admin.py`:
- Нет переопределения `has_*_permission` возвращающего `True` без проверки.
- Нет `list_editable` для чувствительных полей.

### 5. SQL-инъекции и raw queries

Поищи `raw(`, `.execute(`, `extra(` в `testing/`:
- Если есть — убедись что параметры передаются через placeholders, не f-строками.

### 6. Валидация входных данных

Прочитай `testing/serializers.py`:
- Все поля явно объявлены или есть `read_only_fields`.
- Нет `fields = "__all__"` в сериализаторах записи (только для чтения допустимо).

## Формат ответа

Выдай список проблем:

**КРИТИЧНО** — уязвимость, требует немедленного исправления
**ВАЖНО** — риск в продакшене, нужно исправить до деплоя
**РЕКОМЕНДАЦИЯ** — улучшение безопасности, не блокирует

Для каждой проблемы: файл:строка, описание, как исправить.
