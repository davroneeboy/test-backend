Расширь или зарегистрируй модель в Django Admin для этого проекта.

Модель/задача: $ARGUMENTS

## Чеклист

1. Прочитай модель в `testing/models.py` чтобы знать поля.
2. Открой `testing/admin.py` — посмотри существующий стиль регистрации.
3. Создай или дополни `ModelAdmin` по шаблону ниже.
4. Запусти `python manage.py check` и убедись что ошибок нет.

## Шаблон ModelAdmin

```python
@admin.register(YourModel)
class YourModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "created_at")       # + FK user, test
    list_filter = ("status",)                       # + dates via date_hierarchy
    search_fields = ("title", "user__username", "user__email")
    readonly_fields = ("created_at", "updated_at", "duration_seconds")
    date_hierarchy = "finished_at"                  # если есть

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user", "test").prefetch_related("user__groups")

    @admin.display(description="Длительность")
    def duration_display(self, obj):
        return obj.duration_human_readable() if obj.finished_at else "—"
```

## Связанные объекты

- `autocomplete_fields` для FK на `User` при большом числе пользователей (требует `search_fields` у `UserAdmin`).
- `raw_id_fields` как лёгкая альтернатива без autocomplete.
- `TabularInline` / `StackedInline` для ответов внутри карточки попытки.

## Правила проекта

- `verbose_name` и описания — на русском.
- Код — латиница, snake_case.
- Не добавляй `list_editable` для вычисляемых полей.
- Для сортировки вычисляемой колонки укажи `@admin.display(ordering="db_field")`.
