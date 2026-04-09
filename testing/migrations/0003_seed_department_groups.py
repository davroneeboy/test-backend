# Отделы (django.contrib.auth.Group) — разовое заполнение списка.

from django.db import migrations


DEPARTMENT_NAMES = (
    "Sanoatlashtirilgan intensiv bog‘ va uzumzorlarni rivojlantirish boshqarmasi",
    "Ko‘chatchilik xo‘jaliklarini muvofiqlashtirish va himoyasi bo‘limi",
    "Suv tejovchi texnologiyalarni rivojlantirish bo‘limi",
    "Bog‘ va uzumzor, issiqxona yerlardan foydalanishni tashkil etish, yer axborot bazasini yuritish va tuproq unumdorligini aniqlash bo‘limi",
    "Loyihalarni texnik-iqtisodiy asoslash boshqarmasi",
    "Qayta ishlash va qo‘shilgan qiymatni rivojlantirish bo‘limi",
    "Agrologistika va sovutgichli omborlarni rivojlantirish bo‘yicha bosh mutaxassis",
    "Issiqxona xo‘jaliklarini rivojlantirish bo‘limi",
    "Marketing va eksport bo‘limi",
    "Moliyalashtirish, buxgalteriya hisobi va rejalashtirish bo‘limi",
    "Jamg‘arma faoliyatini muvofiqlashtirish bo‘limi",
    "Moliyaviy qo‘llab-quvvatlash bo‘limi",
    "Axborot tahlili va strategik rejalashtirish va metodologiya bo‘limi",
    "Inson resurslarini rivojlantirish va boshqarish bo‘limi",
    "Ijro nazorati bo‘limi",
    "Devonxona va murojaatlar bilan ishlash bo‘yicha bosh mutaxassis",
    "Yuridik ta’minlash bo‘limi",
    "AKTni joriy etish, raqamlashtirish va sun’iy intellektni rivojlantirish bo‘limi",
    "Korrupsiyaga qarshi kurashish bo‘limi",
    "Investitsiyalar va xalqaro aloqalar bo‘limi",
    "Ichki audit bo‘limi",
    "Axborot xizmatlari bo‘limi",
)


def seed_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in DEPARTMENT_NAMES:
        Group.objects.get_or_create(name=name)


def unseed_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=DEPARTMENT_NAMES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("testing", "0002_test_conduct_period"),
    ]

    operations = [
        migrations.RunPython(seed_groups, unseed_groups),
    ]
