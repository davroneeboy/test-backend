Добавь новую модель в домен тестирования этого проекта.

Модель/описание: $ARGUMENTS

## Шаги

1. Прочитай `testing/models.py` — посмотри существующие модели и импорты.
2. Добавь модель по правилам ниже.
3. Если нужна регистрация в Admin — добавь в `testing/admin.py`.
4. Запусти:
   ```bash
   python manage.py makemigrations testing
   python manage.py migrate
   python manage.py check
   ```

## Правила модели

```python
class YourModel(models.Model):
    # Поля с явными verbose_name на русском
    name = models.CharField("название", max_length=255)
    created_at = models.DateTimeField("создано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        verbose_name = "модель"
        verbose_name_plural = "модели"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),  # поля фильтрации
        ]

    def __str__(self):
        return self.name
```

## Связи

- FK с `on_delete=PROTECT` если нельзя удалить родительский объект с дочерними (результаты → тест).
- FK с `on_delete=CASCADE` если дочерние без родителя не имеют смысла.
- `related_name` всегда задавай явно.

## Сущности домена

| Концепт | Модель | Связи |
|---------|--------|-------|
| Отдел | `Group` / `Department` | M2M к User |
| Тест | `Test` | FK от Attempt |
| Попытка | `Attempt` | FK User, FK Test |
| Ответ | `AttemptAnswer` (если нужен) | FK Attempt |

Не дублируй отделы в двух местах — выбери `Group` или отдельную модель и придерживайся одного подхода.
