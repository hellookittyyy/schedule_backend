# Generated migration to add default ClassType records

from django.db import migrations


def add_class_types(apps, schema_editor):
    """
    Додає основні типи занять у базу даних.
    Використовує get_or_create для уникнення дублікатів.
    """
    ClassType = apps.get_model('api', 'ClassType')
    
    class_type_names = [
        "Лекція",
        "Практична",
        "Лабораторна",
        "Екзамен"
    ]
    
    for name in class_type_names:
        ClassType.objects.get_or_create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0019_remove_studyplan_study_plan_group_xor_stream_and_more'),
    ]

    # Reverse is a no-op: study plans reference class types with PROTECT,
    # and the names may have existed before this migration.
    operations = [
        migrations.RunPython(add_class_types, migrations.RunPython.noop),
    ]
