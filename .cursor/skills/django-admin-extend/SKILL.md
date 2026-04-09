---
name: django-admin-extend
description: >-
  Пошаговое добавление и настройка Django ModelAdmin для этого проекта —
  list_display, фильтры, read-only, оптимизация запросов. Используй при
  регистрации новых моделей в админке, доработке списков и детальных форм
  тестов или результатов.
---

# Расширение Django Admin

## Чеклист новой модели в админке

1. Импорт: `from django.contrib import admin` и модель
2. Класс `YourModelAdmin(admin.ModelAdmin)` с полями ниже по необходимости
3. `@admin.register(YourModel)` над классом

## Поля ModelAdmin (типовой набор)

```python
list_display = ("__str__", "created_at")  # + FK к user, test
list_filter = ("is_active",)  # + даты через date_hierarchy
search_fields = ("title", "user__username", "user__email")
readonly_fields = ("created_at", "updated_at", "duration_seconds")
date_hierarchy = "finished_at"  # если есть
```

## Связанные объекты

- `autocomplete_fields` для FK на `User` при большом числе пользователей (нужен `search_fields` у UserAdmin)
- `raw_id_fields` как лёгкая альтернатива без autocomplete

## Оптимизация

```python
def get_queryset(self, request):
    qs = super().get_queryset(request)
    return qs.select_related("user", "test").prefetch_related("user__groups")
```

## Вычисляемые колонки

```python
@admin.display(description="Длительность")
def duration_display(self, obj):
    return obj.duration_human_readable() if obj.finished_at else "—"
```

Добавь имя метода в `list_display`; для сортировки укажи `admin.display(ordering=...)`, если сортируемое поле есть в БД.

## Inline

- `TabularInline` / `StackedInline` для ответов на вопросы внутри карточки попытки

## После правок

Запусти проверку: `python manage.py check` и при необходимости тесты проекта.
