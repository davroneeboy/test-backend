Добавь новый API-эндпоинт в DRF-слой этого проекта.

Описание эндпоинта: $ARGUMENTS

## Шаги

1. Прочитай `testing/api_views.py`, `testing/serializers.py`, `testing/urls_api.py` — понять текущую структуру.
2. Прочитай `testing/models.py` — понять данные.
3. Если нужна бизнес-логика — добавь в `testing/services.py`, не в сериализатор.
4. Создай/расширь сериализатор в `serializers.py`.
5. Создай вьюсет или APIView в `api_views.py`.
6. Зарегистрируй маршрут в `urls_api.py`.
7. Добавь права доступа через `testing/permissions.py` или встроенные DRF.
8. Запусти тесты: `python manage.py test testing`.

## Структура

```
testing/
├── api_views.py      # ViewSet / APIView
├── serializers.py    # сериализаторы
├── services.py       # бизнес-логика (не в сериализаторах!)
├── permissions.py    # кастомные права
├── urls_api.py       # router + urlpatterns
└── api_exceptions.py # кастомные исключения
```

## Шаблон ViewSet

```python
class YourModelViewSet(viewsets.ModelViewSet):
    serializer_class = YourModelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return YourModel.objects.select_related("user", "test").filter(
            user=self.request.user
        )
```

## Шаблон кастомного action

```python
@action(detail=True, methods=["post"], url_path="submit")
def submit(self, request, pk=None):
    obj = self.get_object()
    result = some_service.process(obj, request.data)
    return Response(YourSerializer(result).data)
```

## Правила

- Бизнес-логика — в `services.py`, не в view и не в сериализаторе.
- `select_related` / `prefetch_related` в `get_queryset`.
- Кастомные ошибки — через `api_exceptions.py`.
- Минимум `IsAuthenticated` на всех эндпоинтах.
