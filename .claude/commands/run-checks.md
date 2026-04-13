Запусти стандартные проверки проекта и сообщи о результатах.

## Команды

```bash
python manage.py check --deploy 2>/dev/null || python manage.py check
python manage.py test testing --verbosity=2
```

Если тесты падают — прочитай traceback, найди причину в коде и предложи исправление.

Если `check` выдаёт предупреждения — объясни каждое и скажи, критично ли оно для разработки.
