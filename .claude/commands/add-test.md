Напиши тест для указанного кода в этом проекте.

Что тестировать: $ARGUMENTS

## Шаги

1. Прочитай `testing/tests.py` и `testing/test_api.py` — посмотри существующий стиль.
2. Прочитай код, который нужно тестировать.
3. Напиши тест в подходящем файле по правилам ниже.
4. Запусти: `python manage.py test testing --verbosity=2`

## Структура тестов проекта

```
testing/tests.py      # unit-тесты моделей, сервисов
testing/test_api.py   # интеграционные тесты DRF API
```

## Шаблон unit-теста

```python
from django.test import TestCase
from django.contrib.auth import get_user_model
from testing.models import YourModel

User = get_user_model()

class YourModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="test", password="pass")

    def test_something(self):
        obj = YourModel.objects.create(user=self.user, ...)
        self.assertEqual(obj.some_field, expected_value)
```

## Шаблон API-теста

```python
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model

User = get_user_model()

class YourEndpointTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="test", password="pass")
        self.client.force_authenticate(user=self.user)

    def test_list(self):
        response = self.client.get("/api/your-endpoint/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
```

## Правила

- Используй реальную БД (SQLite в тестах), не мокай ORM.
- Один тест — одно утверждение или логически связанная группа.
- Тестируй граничные случаи: пустой queryset, нет прав, невалидные данные.
- Для Admin-действий используй `django.test.Client` с `staff`-пользователем.
