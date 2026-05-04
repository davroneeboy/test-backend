from dataclasses import dataclass
from typing import Optional

import openpyxl
from django.contrib.auth.models import Group
from django.db import transaction

from .models import AnswerOption, Question, QuestionGroup, Test

# Excel layout (0-based column indices):
# A(0)  — group / department name (optional)
# B(1)  — question text
# C(2)  — points (default 1)
# D-K(3-10) — answer options (up to 8, blank cells skipped)
# L(11) — correct answer(s), 1-based, comma-separated (e.g. "1" or "1,3")
_OPTION_START = 3
_OPTION_END = 11   # exclusive
_CORRECT_COL = 11


class ParseError(Exception):
    pass


@dataclass
class _Row:
    group_name: str
    question_text: str
    points: int
    options: list
    correct_indices: list  # 0-based into options


def _cell(row, idx: int) -> str:
    if idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


def parse_excel(file_obj) -> list:
    """Parse uploaded .xlsx, return list[_Row]. Raise ParseError on invalid data."""
    try:
        wb = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
    except Exception as exc:
        raise ParseError(f"Не удалось открыть файл: {exc}")

    ws = wb.active
    all_rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not all_rows:
        raise ParseError("Файл пустой.")

    results = []
    for row_num, raw in enumerate(all_rows[1:], start=2):
        if not any(v for v in raw if v is not None):
            continue

        group_name = _cell(raw, 0)
        question_text = _cell(raw, 1)
        if not question_text:
            raise ParseError(f"Строка {row_num}: текст вопроса пустой.")

        raw_points = _cell(raw, 2)
        try:
            points = max(1, int(float(raw_points))) if raw_points else 1
        except ValueError:
            points = 1

        options = [
            _cell(raw, i)
            for i in range(_OPTION_START, _OPTION_END)
            if _cell(raw, i)
        ]
        if len(options) < 2:
            raise ParseError(f"Строка {row_num}: нужно минимум 2 варианта ответа (столбцы D–K).")

        correct_raw = _cell(raw, _CORRECT_COL)
        if not correct_raw:
            raise ParseError(f"Строка {row_num}: не указан правильный ответ (столбец L).")

        try:
            correct_nums = [int(x.strip()) for x in correct_raw.split(",") if x.strip()]
        except ValueError:
            raise ParseError(
                f"Строка {row_num}: неверный формат правильного ответа «{correct_raw}». "
                "Укажите номера через запятую, например: 1 или 1,3"
            )

        if not correct_nums:
            raise ParseError(f"Строка {row_num}: не указан правильный ответ (столбец L).")

        correct_indices = []
        for n in correct_nums:
            idx = n - 1
            if idx < 0 or idx >= len(options):
                raise ParseError(
                    f"Строка {row_num}: правильный ответ {n} выходит за пределы "
                    f"(вариантов заполнено: {len(options)})."
                )
            correct_indices.append(idx)

        results.append(_Row(
            group_name=group_name,
            question_text=question_text,
            points=points,
            options=options,
            correct_indices=correct_indices,
        ))

    if not results:
        raise ParseError("Нет данных: все строки пустые.")

    return results


def import_test(
    title: str,
    description: str,
    time_limit_seconds: Optional[int],
    questions_to_show: Optional[int],
    rows: list,
) -> Test:
    """Create Test, QuestionGroups, Questions, AnswerOptions atomically. Return Test."""
    with transaction.atomic():
        test = Test.objects.create(
            title=title,
            description=description or "",
            time_limit_seconds=time_limit_seconds,
            questions_to_show=questions_to_show,
        )

        groups_cache: dict = {}  # group_name -> QuestionGroup

        for order, row in enumerate(rows):
            qgroup = None
            if row.group_name:
                if row.group_name not in groups_cache:
                    dept = Group.objects.filter(name=row.group_name).first()
                    qgroup = QuestionGroup.objects.create(
                        test=test,
                        department=dept,
                        order=len(groups_cache),
                    )
                    groups_cache[row.group_name] = qgroup
                else:
                    qgroup = groups_cache[row.group_name]

            question = Question.objects.create(
                test=test,
                group=qgroup,
                text=row.question_text,
                points=row.points,
                order=order,
            )

            for opt_i, opt_text in enumerate(row.options):
                AnswerOption.objects.create(
                    question=question,
                    text=opt_text,
                    is_correct=(opt_i in row.correct_indices),
                )

        return test
