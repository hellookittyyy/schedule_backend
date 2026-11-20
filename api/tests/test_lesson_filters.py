"""Lesson filters and study-plan ids for the public page (plan phase 4)."""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from api.models import Lesson
from api.tests.factories import (
    make_class_type,
    make_group,
    make_lesson,
    make_semester,
    make_stream,
    make_study_plan,
    make_subject,
    make_teacher,
)

LESSONS_URL = '/api/lessons/'


class LessonFilterTests(APITestCase):
    def make_semester_with_slots(self):
        semester = make_semester()
        semester.synchronize_slots()
        return semester

    def setUp(self):
        self.plan_count = 0

    def make_plan(self, semester, **kwargs):
        if 'class_type' not in kwargs:
            self.plan_count += 1
            kwargs['class_type'] = make_class_type(name=f'Тестовий тип {self.plan_count}')
        return make_study_plan(semester, **kwargs)

    def slots(self, semester):
        return list(semester.timeslots.order_by('date', 'period_number'))

    def get_ids(self, query):
        response = self.client.get(LESSONS_URL, query)
        self.assertEqual(response.status_code, 200)
        return sorted(item['id'] for item in response.data)


class StudyPlanIdPayloadTests(LessonFilterTests):
    def test_group_plan_exposes_group_id_and_null_stream_id(self):
        semester = self.make_semester_with_slots()
        group = make_group(name='КН-1')
        subject = make_subject(name='Алгебра')
        teacher = make_teacher(name='Сидоренко П. П.')
        class_type = make_class_type(name='Лекція тестова')
        plan = self.make_plan(
            semester,
            subject=subject,
            teacher=teacher,
            class_type=class_type,
            group=group,
        )
        lesson = make_lesson(plan, time_slot=self.slots(semester)[0])

        response = self.client.get(LESSONS_URL, {'study_plan': plan.id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        details = response.data[0]['study_plan_details']
        self.assertEqual(details['group_id'], group.id)
        self.assertIsNone(details['stream_id'])
        self.assertEqual(details['teacher_id'], teacher.id)
        self.assertEqual(details['subject_id'], subject.id)
        self.assertEqual(details['class_type_id'], class_type.id)
        # Name fields stay in the payload.
        self.assertEqual(details['group'], 'КН-1')
        self.assertEqual(details['subject'], 'Алгебра')
        self.assertEqual(details['teacher'], 'Сидоренко П. П.')
        self.assertEqual(details['class_type'], 'Лекція тестова')
        self.assertIsNone(details['stream'])
        self.assertIn('duration', details)

    def test_stream_plan_exposes_stream_id_and_null_group_id(self):
        semester = self.make_semester_with_slots()
        group = make_group(name='КН-2')
        stream = make_stream(name='Потік КН', groups=[group])
        plan = self.make_plan(semester, stream=stream)
        make_lesson(plan, time_slot=self.slots(semester)[0])

        response = self.client.get(LESSONS_URL, {'study_plan': plan.id})

        self.assertEqual(response.status_code, 200)
        details = response.data[0]['study_plan_details']
        self.assertEqual(details['stream_id'], stream.id)
        self.assertIsNone(details['group_id'])
        self.assertEqual(details['stream'], 'Потік КН')
        self.assertIsNone(details['group'])


class ForGroupTests(LessonFilterTests):
    def test_for_group_returns_own_and_stream_lessons_without_duplicates(self):
        semester = self.make_semester_with_slots()
        slots = self.slots(semester)
        group = make_group(name='КН-3')
        other_group = make_group(name='КН-4')
        stream = make_stream(name='Потік КН-3', groups=[group])

        own_plan = self.make_plan(semester, group=group)
        stream_plan = self.make_plan(semester, stream=stream)
        other_plan = self.make_plan(semester, group=other_group)

        own_lesson = make_lesson(own_plan, time_slot=slots[0])
        stream_lesson = make_lesson(stream_plan, time_slot=slots[1])
        make_lesson(other_plan, time_slot=slots[2])

        ids = self.get_ids({'for_group': group.id})

        self.assertEqual(ids, sorted([own_lesson.id, stream_lesson.id]))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 2)

    def test_same_name_streams_do_not_leak(self):
        semester = self.make_semester_with_slots()
        slots = self.slots(semester)
        group_a = make_group(name='КН-5')
        group_b = make_group(name='КН-6')
        stream_a = make_stream(name='Потік X', groups=[group_a])
        stream_b = make_stream(name='Потік X', groups=[group_b])

        self.make_plan(semester, stream=stream_a)
        plan_b = self.make_plan(semester, stream=stream_b)
        lesson_b = make_lesson(plan_b, time_slot=slots[0])

        ids = self.get_ids({'for_group': group_a.id})
        self.assertEqual(ids, [])

        ids = self.get_ids({'for_group': group_b.id})
        self.assertEqual(ids, [lesson_b.id])

    def test_group_id_still_means_own_group_plans_only(self):
        semester = self.make_semester_with_slots()
        slots = self.slots(semester)
        group = make_group(name='КН-7')
        stream = make_stream(name='Потік КН-7', groups=[group])

        own_plan = self.make_plan(semester, group=group)
        stream_plan = self.make_plan(semester, stream=stream)
        own_lesson = make_lesson(own_plan, time_slot=slots[0])
        make_lesson(stream_plan, time_slot=slots[1])

        self.assertEqual(self.get_ids({'group_id': group.id}), [own_lesson.id])


class TeacherFilterTests(LessonFilterTests):
    def test_teacher_id_is_exact_and_teacher_name_is_icontains(self):
        semester = self.make_semester_with_slots()
        slots = self.slots(semester)
        short_name = make_teacher(name='Петренко Олена')
        long_name = make_teacher(name='Петренко Олена Іванівна')

        short_plan = self.make_plan(semester, teacher=short_name)
        long_plan = self.make_plan(semester, teacher=long_name)
        short_lesson = make_lesson(short_plan, time_slot=slots[0])
        long_lesson = make_lesson(long_plan, time_slot=slots[1])

        by_name = self.get_ids({'teacher_name': 'Петренко Олена'})
        self.assertEqual(by_name, sorted([short_lesson.id, long_lesson.id]))

        by_id = self.get_ids({'teacher_id': short_name.id})
        self.assertEqual(by_id, [short_lesson.id])


class LessonQueryCountTests(LessonFilterTests):
    def test_query_count_is_constant(self):
        semester = self.make_semester_with_slots()
        slots = self.slots(semester)
        plan = self.make_plan(semester)
        make_lesson(plan, time_slot=slots[0])
        make_lesson(plan, time_slot=slots[1])

        query = {'study_plan__semester': semester.id}

        with CaptureQueriesContext(connection) as first:
            response = self.client.get(LESSONS_URL, query)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data), 2)

        for index in range(2, 20):
            make_lesson(plan, time_slot=slots[index])

        with CaptureQueriesContext(connection) as second:
            response = self.client.get(LESSONS_URL, query)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data), 20)

        self.assertEqual(len(second), len(first))
        self.assertEqual(Lesson.objects.filter(study_plan__semester=semester).count(), 20)
