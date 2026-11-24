from datetime import date, time

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


MIGRATE_FROM = [('api', '0020_add_class_types')]
MIGRATE_TO = [('api', '0021_alter_timeslot_unique_together')]


def _make_historical_plan(apps, semester, group_name='Г-1'):
    Group = apps.get_model('api', 'Group')
    Subject = apps.get_model('api', 'Subject')
    Teacher = apps.get_model('api', 'Teacher')
    ClassType = apps.get_model('api', 'ClassType')
    StudyPlan = apps.get_model('api', 'StudyPlan')

    group = Group.objects.create(name=group_name, amount=20, start_year=2024)
    subject = Subject.objects.create(name='Математика')
    teacher = Teacher.objects.create(name='Іваненко І. І.')
    # 0020 вже сіє типи занять, тому не створюємо дублікат.
    class_type, _ = ClassType.objects.get_or_create(name='Лекція')
    return StudyPlan.objects.create(
        semester=semester,
        group=group,
        subject=subject,
        teacher=teacher,
        class_type=class_type,
        amount=1,
        duration=1,
    )


def _make_historical_room(apps, room_type, title):
    Room = apps.get_model('api', 'Room')
    return Room.objects.create(
        title=title, building='1', capacity=30, room_type=room_type
    )


def _make_historical_room_type(apps, name='Лекційна'):
    RoomType = apps.get_model('api', 'RoomType')
    return RoomType.objects.create(name=name)


class Migration0021Tests(TransactionTestCase):
    """Перевіряє RunPython-кроки міграції 0021 на стані 0020."""

    migrate_from = MIGRATE_FROM
    migrate_to = MIGRATE_TO

    def setUp(self):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.migrate_from)
        self.old_apps = self.executor.loader.project_state(self.migrate_from).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def _migrate_forward(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)

    def test_renumbers_mislabeled_slots(self):
        Semester = self.old_apps.get_model('api', 'Semester')
        TimeSlot = self.old_apps.get_model('api', 'TimeSlot')
        Lesson = self.old_apps.get_model('api', 'Lesson')

        semester = Semester.objects.create(
            name='Семестр 1',
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 20),
            configuration={
                'time_schedule': [['08:30', '09:50'], ['10:00', '11:20']],
                'weekends': [],
            },
        )
        first = TimeSlot.objects.create(
            semester=semester,
            date=date(2026, 9, 1),
            period_number=1,
            start_time=time(8, 30),
            end_time=time(9, 50),
        )
        second = TimeSlot.objects.create(
            semester=semester,
            date=date(2026, 9, 1),
            period_number=1,
            start_time=time(10, 0),
            end_time=time(11, 20),
        )
        plan = _make_historical_plan(self.old_apps, semester)
        lesson = Lesson.objects.create(study_plan=plan, time_slot=first)

        self._migrate_forward()

        self.assertEqual(TimeSlot.objects.filter(semester_id=semester.pk).count(), 2)
        first_after = TimeSlot.objects.get(pk=first.pk)
        second_after = TimeSlot.objects.get(pk=second.pk)
        self.assertEqual(first_after.period_number, 1)
        self.assertEqual(second_after.period_number, 2)

        self.assertEqual(Lesson.objects.count(), 1)
        self.assertEqual(Lesson.objects.get(pk=lesson.pk).time_slot_id, first.pk)

    def test_dedupes_true_copies_and_unplaces_room_clash(self):
        Semester = self.old_apps.get_model('api', 'Semester')
        TimeSlot = self.old_apps.get_model('api', 'TimeSlot')
        Lesson = self.old_apps.get_model('api', 'Lesson')

        semester = Semester.objects.create(
            name='Семестр 1',
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 20),
            configuration={
                'time_schedule': [['08:30', '09:50']],
                'weekends': [],
            },
        )
        low = TimeSlot.objects.create(
            semester=semester,
            date=date(2026, 9, 1),
            period_number=1,
            start_time=time(8, 30),
            end_time=time(9, 50),
        )
        high = TimeSlot.objects.create(
            semester=semester,
            date=date(2026, 9, 1),
            period_number=1,
            start_time=time(8, 30),
            end_time=time(9, 50),
        )

        room_type = _make_historical_room_type(self.old_apps)
        room_r = _make_historical_room(self.old_apps, room_type, 'R')
        room_r2 = _make_historical_room(self.old_apps, room_type, 'R2')
        plan = _make_historical_plan(self.old_apps, semester)

        # Обидва слоти однакові за (date, period, start_time), тому міграція
        # лишає той, де більше занять. Тут це high, хоча його id більший:
        # нижчий id має лише 2 заняття проти 3.
        low_clash = Lesson.objects.create(study_plan=plan, time_slot=low, room=room_r)
        low_movable = Lesson.objects.create(study_plan=plan, time_slot=low, room=room_r2)
        high_with_r = Lesson.objects.create(study_plan=plan, time_slot=high, room=room_r)
        high_unplaced = [
            Lesson.objects.create(study_plan=plan, time_slot=high) for _ in range(2)
        ]

        self._migrate_forward()

        remaining = TimeSlot.objects.filter(
            semester_id=semester.pk, date=date(2026, 9, 1), period_number=1
        )
        self.assertEqual(remaining.count(), 1)
        self.assertEqual(remaining.get().pk, high.pk)
        self.assertFalse(TimeSlot.objects.filter(pk=low.pk).exists())

        self.assertEqual(Lesson.objects.count(), 5)
        self.assertIsNone(Lesson.objects.get(pk=low_clash.pk).time_slot_id)
        self.assertEqual(Lesson.objects.get(pk=low_movable.pk).time_slot_id, high.pk)
        self.assertEqual(Lesson.objects.get(pk=high_with_r.pk).time_slot_id, high.pk)
        for lesson in high_unplaced:
            self.assertEqual(Lesson.objects.get(pk=lesson.pk).time_slot_id, high.pk)
