Добавь экспорт данных в CSV или Excel из Django Admin.

Что экспортировать: $ARGUMENTS

## Шаги

1. Прочитай `testing/admin.py` — найди нужный `ModelAdmin`.
2. Прочитай `testing/models.py` — знай поля модели.
3. Реализуй action по шаблону ниже.
4. Запусти `python manage.py check`.

## Шаблон CSV-экспорта (без зависимостей)

```python
import csv
from django.http import HttpResponse

@admin.action(description="Экспорт в CSV")
def export_csv(modeladmin, request, queryset):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="export.csv"'
    response.write("\ufeff")  # BOM для корректного открытия в Excel

    writer = csv.writer(response)
    writer.writerow([
        "Пользователь", "Тест", "Отдел",
        "Начало", "Конец", "Длительность (с)", "Балл", "Статус",
    ])

    qs = queryset.select_related("user", "test").prefetch_related("user__groups")
    for obj in qs:
        department = obj.user.groups.first().name if obj.user.groups.exists() else "—"
        writer.writerow([
            obj.user.get_full_name() or obj.user.username,
            str(obj.test),
            department,
            obj.started_at.strftime("%d.%m.%Y %H:%M") if obj.started_at else "—",
            obj.finished_at.strftime("%d.%m.%Y %H:%M") if obj.finished_at else "—",
            obj.duration_seconds if hasattr(obj, "duration_seconds") else "—",
            obj.score if hasattr(obj, "score") else "—",
            obj.get_status_display() if hasattr(obj, "get_status_display") else "—",
        ])

    return response
```

Добавь в `ModelAdmin`:
```python
actions = [export_csv]
```

## Шаблон Excel-экспорта (через openpyxl)

Используй только если `openpyxl` уже есть в `requirements.txt`. Если нет — предложи добавить или используй CSV.

```python
import openpyxl
from django.http import HttpResponse

@admin.action(description="Экспорт в Excel")
def export_xlsx(modeladmin, request, queryset):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Результаты"

    headers = ["Пользователь", "Тест", "Отдел", "Дата", "Балл", "Статус"]
    ws.append(headers)

    for obj in queryset.select_related("user", "test"):
        ws.append([
            obj.user.get_full_name() or obj.user.username,
            str(obj.test),
            obj.user.groups.first().name if obj.user.groups.exists() else "—",
            obj.finished_at.strftime("%d.%m.%Y") if obj.finished_at else "—",
            getattr(obj, "score", "—"),
            obj.get_status_display() if hasattr(obj, "get_status_display") else "—",
        ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="export.xlsx"'
    wb.save(response)
    return response
```

## Правила

- Используй `select_related` / `prefetch_related` — не делай N+1 запросов при экспорте.
- CSV с BOM (`\ufeff`) — Excel на Windows открывает кириллицу корректно.
- Имя файла в `Content-Disposition` — на латинице или транслитом (кириллица в заголовках ломает некоторые браузеры).
- Для больших выборок (>10k строк) рассмотри `iterator()` на queryset.
