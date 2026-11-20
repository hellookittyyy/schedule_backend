"""Невеликі детерміновані фабрики моделей для тестів API."""

from datetime import date

from api.models import (
    ClassType,
    Group,
    Lesson,
    Room,
    RoomType,
    Semester,
    Stream,
    StudyPlan,
    Subject,
    Teacher,
)

DEFAULT_TIME_SCHEDULE = [
    ['08:30', '09:50'],
    ['10:00', '11:20'],
    ['11:40', '13:00'],
]


def make_semester(
    name='Семестр 1',
    start_date=date(2026, 9, 1),
    end_date=date(2026, 12, 20),
    config=None,
    is_current=False,
):
    if config is None:
        config = {
            'time_schedule': [list(pair) for pair in DEFAULT_TIME_SCHEDULE],
            'weekends': ['Saturday', 'Sunday'],
        }
    return Semester.objects.create(
        name=name,
        start_date=start_date,
        end_date=end_date,
        configuration=config,
        is_current=is_current,
    )


def make_group(name='Г-1', amount=20, start_year=2024):
    return Group.objects.create(name=name, amount=amount, start_year=start_year)


def make_stream(name='Потік 1', groups=()):
    stream = Stream.objects.create(name=name)
    stream.groups.set(groups)
    return stream


def make_subject(name='Математика'):
    return Subject.objects.create(name=name)


def make_teacher(name='Іваненко І. І.', subjects=()):
    teacher = Teacher.objects.create(name=name)
    teacher.subjects.set(subjects)
    return teacher


def make_class_type(name='Лекція'):
    return ClassType.objects.get_or_create(name=name)[0]


def make_room_type(name='Лекційна'):
    return RoomType.objects.create(name=name)


def make_room(title='101', building='1', capacity=30, room_type=None):
    if room_type is None:
        room_type = make_room_type()
    return Room.objects.create(
        title=title,
        building=building,
        capacity=capacity,
        room_type=room_type,
    )


def make_study_plan(
    semester,
    subject=None,
    teacher=None,
    class_type=None,
    group=None,
    stream=None,
    amount=1,
    duration=1,
):
    if group is not None and stream is not None:
        raise ValueError("Вкажіть або групу, або потік, не обидва.")
    subject = subject or make_subject()
    teacher = teacher or make_teacher()
    class_type = class_type or make_class_type()
    if group is None and stream is None:
        group = make_group()
    return StudyPlan.objects.create(
        semester=semester,
        subject=subject,
        teacher=teacher,
        class_type=class_type,
        group=group,
        stream=stream,
        amount=amount,
        duration=duration,
    )


def make_lesson(study_plan, time_slot=None, room=None, is_locked=False):
    return Lesson.objects.create(
        study_plan=study_plan,
        time_slot=time_slot,
        room=room,
        is_locked=is_locked,
    )
