"""Semester edit with an existing schedule: re-sync rules, 409 and forced delete."""

from datetime import date
from unittest.mock import patch

from rest_framework.test import APITestCase

from api.models import Lesson, Semester, TimeSlot
from api.tests.factories import (
    DEFAULT_TIME_SCHEDULE,
    make_class_type,
    make_lesson,
    make_semester,
    make_study_plan,
)

SHORT_START = date(2026, 9, 1)   # Tuesday
SHORT_END = date(2026, 9, 4)     # Friday → 4 weekdays
NEW_START = date(2026, 9, 7)     # Monday
NEW_END = date(2026, 9, 8)       # Tuesday → 2 weekdays


def base_config():
    return {
        'time_schedule': [list(pair) for pair in DEFAULT_TIME_SCHEDULE],
        'weekends': ['Saturday', 'Sunday'],
    }


def two_pair_config():
    return {
        'time_schedule': [list(pair) for pair in DEFAULT_TIME_SCHEDULE[:2]],
        'weekends': ['Saturday', 'Sunday'],
    }


class SemesterEditTests(APITestCase):
    def make_semester_with_slots(self, config=None):
        semester = make_semester(
            start_date=SHORT_START,
            end_date=SHORT_END,
            config=config or base_config(),
        )
        semester.synchronize_slots()
        return semester

    def make_plan(self, semester):
        return make_study_plan(semester, class_type=make_class_type(name="Семінар"))

    def full_payload(self, semester, **overrides):
        payload = {
            'name': semester.name,
            'start_date': semester.start_date.isoformat(),
            'end_date': semester.end_date.isoformat(),
            'is_current': semester.is_current,
        }
        payload.update(overrides)
        return payload

    def slot_ids(self, semester):
        return set(semester.timeslots.values_list('id', flat=True))

    def lesson_state(self):
        return list(Lesson.objects.values_list('id', 'time_slot_id', 'is_locked'))

    # --- create -----------------------------------------------------------

    def test_create_semester_with_generation_config(self):
        response = self.client.post(
            '/api/semesters/',
            {
                'name': 'Новий',
                'start_date': SHORT_START.isoformat(),
                'end_date': SHORT_END.isoformat(),
                'generation_config': base_config(),
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.content)
        semester = Semester.objects.get(pk=response.data['id'])
        self.assertEqual(semester.timeslots.count(), 4 * 3)

    def test_create_semester_without_generation_config(self):
        response = self.client.post(
            '/api/semesters/',
            {
                'name': 'Новий',
                'start_date': SHORT_START.isoformat(),
                'end_date': SHORT_END.isoformat(),
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.content)
        semester = Semester.objects.get(pk=response.data['id'])
        self.assertEqual(semester.timeslots.count(), 0)

    # --- edits that must not touch the schedule ---------------------------

    def test_patch_name_only_keeps_lessons(self):
        semester = self.make_semester_with_slots()
        plan = self.make_plan(semester)
        slot = semester.timeslots.first()
        make_lesson(plan, time_slot=slot)

        response = self.client.patch(
            f'/api/semesters/{semester.pk}/', {'name': 'Перейменований'}, format='json'
        )

        self.assertEqual(response.status_code, 200, response.content)
        semester.refresh_from_db()
        self.assertEqual(semester.name, 'Перейменований')
        self.assertEqual(self.lesson_state(), [(Lesson.objects.get().pk, slot.pk, False)])

    def test_put_name_only_with_confirm_keeps_lessons(self):
        semester = self.make_semester_with_slots()
        plan = self.make_plan(semester)
        slot = semester.timeslots.first()
        make_lesson(plan, time_slot=slot)

        payload = self.full_payload(
            semester, name='Перейменований', confirm_schedule_deletion=True
        )
        response = self.client.put(f'/api/semesters/{semester.pk}/', payload, format='json')

        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn('deleted_lessons', response.data)
        self.assertEqual(Lesson.objects.count(), 1)
        self.assertEqual(Lesson.objects.get().time_slot_id, slot.pk)

    def test_put_config_non_slot_key_keeps_lessons_and_slots(self):
        semester = self.make_semester_with_slots()
        plan = self.make_plan(semester)
        slot = semester.timeslots.first()
        make_lesson(plan, time_slot=slot)
        slots_before = self.slot_ids(semester)

        config = base_config()
        config['dates_excluded'] = ['2026-09-02']
        payload = self.full_payload(semester, generation_config=config)
        response = self.client.put(f'/api/semesters/{semester.pk}/', payload, format='json')

        self.assertEqual(response.status_code, 200, response.content)
        semester.refresh_from_db()
        self.assertEqual(semester.configuration.get('dates_excluded'), ['2026-09-02'])
        self.assertEqual(self.slot_ids(semester), slots_before)
        self.assertEqual(Lesson.objects.count(), 1)
        self.assertEqual(Lesson.objects.get().time_slot_id, slot.pk)

    # --- edits that need a re-sync, with lessons --------------------------

    def test_put_changed_dates_without_confirm_conflicts(self):
        semester = self.make_semester_with_slots()
        plan = self.make_plan(semester)
        slot = semester.timeslots.first()
        make_lesson(plan, time_slot=slot)
        slots_before = self.slot_ids(semester)
        lessons_before = self.lesson_state()

        payload = self.full_payload(
            semester, start_date=NEW_START.isoformat(), end_date=NEW_END.isoformat()
        )
        response = self.client.put(f'/api/semesters/{semester.pk}/', payload, format='json')

        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.data['code'], 'schedule_exists')
        self.assertTrue(response.data['detail'])

        semester.refresh_from_db()
        self.assertEqual(semester.start_date, SHORT_START)
        self.assertEqual(semester.end_date, SHORT_END)
        self.assertEqual(self.slot_ids(semester), slots_before)
        self.assertEqual(self.lesson_state(), lessons_before)

    def test_put_changed_dates_with_confirm_deletes_lessons_and_resyncs(self):
        semester = self.make_semester_with_slots()
        plan = self.make_plan(semester)
        make_lesson(plan, time_slot=semester.timeslots.first())
        make_lesson(
            plan,
            time_slot=semester.timeslots.filter(period_number=2).first(),
            is_locked=True,
        )

        payload = self.full_payload(
            semester,
            start_date=NEW_START.isoformat(),
            end_date=NEW_END.isoformat(),
            confirm_schedule_deletion=True,
        )
        response = self.client.put(f'/api/semesters/{semester.pk}/', payload, format='json')

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data['deleted_lessons'], 2)
        self.assertEqual(
            Lesson.objects.filter(study_plan__semester=semester).count(), 0
        )

        semester.refresh_from_db()
        self.assertEqual(semester.start_date, NEW_START)
        self.assertEqual(semester.end_date, NEW_END)

        slots = list(TimeSlot.objects.filter(semester=semester))
        self.assertEqual(len(slots), 2 * 3)
        periods_by_date = {}
        for slot in slots:
            self.assertTrue(NEW_START <= slot.date <= NEW_END)
            periods_by_date.setdefault(slot.date, []).append(slot.period_number)
        self.assertEqual(set(periods_by_date), {NEW_START, NEW_END})
        for periods in periods_by_date.values():
            self.assertEqual(sorted(periods), [1, 2, 3])

    def test_put_changed_time_schedule_without_lessons_resyncs(self):
        semester = self.make_semester_with_slots()

        payload = self.full_payload(semester, generation_config=two_pair_config())
        response = self.client.put(f'/api/semesters/{semester.pk}/', payload, format='json')

        self.assertEqual(response.status_code, 200, response.content)
        slots = list(TimeSlot.objects.filter(semester=semester))
        self.assertEqual(len(slots), 4 * 2)
        self.assertEqual({slot.period_number for slot in slots}, {1, 2})

    # --- sync_slots endpoint ---------------------------------------------

    def test_sync_slots_force_keeps_locked_lesson_on_surviving_slot(self):
        semester = self.make_semester_with_slots()
        plan = self.make_plan(semester)
        survivor = semester.timeslots.filter(period_number=1).first()
        locked = make_lesson(plan, time_slot=survivor, is_locked=True)
        unlocked = make_lesson(plan, time_slot=semester.timeslots.filter(period_number=2).first())

        response = self.client.post(
            f'/api/semesters/{semester.pk}/sync_slots/', {'force_delete': True}, format='json'
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(Lesson.objects.filter(pk=locked.pk, time_slot_id=survivor.pk).exists())
        self.assertFalse(Lesson.objects.filter(pk=unlocked.pk).exists())

    def test_sync_slots_force_unplaces_locked_lesson_on_removed_slot(self):
        semester = self.make_semester_with_slots()
        plan = self.make_plan(semester)
        locked = make_lesson(
            plan, time_slot=semester.timeslots.filter(period_number=3).first(), is_locked=True
        )

        semester.configuration = two_pair_config()
        semester.save()

        response = self.client.post(
            f'/api/semesters/{semester.pk}/sync_slots/', {'force_delete': True}, format='json'
        )

        self.assertEqual(response.status_code, 200, response.content)
        locked.refresh_from_db()
        self.assertIsNone(locked.time_slot_id)
        slots = TimeSlot.objects.filter(semester=semester)
        self.assertEqual({slot.period_number for slot in slots}, {1, 2})

    def test_sync_slots_without_force_conflicts(self):
        semester = self.make_semester_with_slots()
        plan = self.make_plan(semester)
        slot = semester.timeslots.first()
        make_lesson(plan, time_slot=slot)
        slots_before = self.slot_ids(semester)
        lessons_before = self.lesson_state()

        response = self.client.post(f'/api/semesters/{semester.pk}/sync_slots/', {}, format='json')

        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.data['code'], 'schedule_exists')
        self.assertEqual(self.slot_ids(semester), slots_before)
        self.assertEqual(self.lesson_state(), lessons_before)

    def test_sync_slots_maps_model_value_error_to_409(self):
        semester = self.make_semester_with_slots()

        # Pre-check бачить порожній розклад, тож ValueError приходить саме з
        # моделі — перевіряємо мапінг винятку у відповідь 409.
        with patch.object(
            Semester, 'synchronize_slots', side_effect=ValueError('boom')
        ):
            response = self.client.post(
                f'/api/semesters/{semester.pk}/sync_slots/',
                {'force_delete': True},
                format='json',
            )

        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.data['code'], 'schedule_exists')
        self.assertEqual(response.data['detail'], 'boom')
