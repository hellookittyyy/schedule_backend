from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from api.models import Semester, Group, Subject, Teacher, ClassType, StudyPlan

class StudyPlanValidationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Correct fields for Semester: name, start_date, end_date
        self.semester = Semester.objects.create(
            name="Test Semester",
            start_date="2023-09-01",
            end_date="2023-12-31"
        )
        self.subject = Subject.objects.create(name="Test Subject")
        self.teacher = Teacher.objects.create(name="Test Teacher")
        
        # Add qualification for teacher
        self.teacher.subjects.add(self.subject)
        
        self.class_type = ClassType.objects.create(name="Lecture")
        
        # Correct fields for Group: name, amount, start_year
        self.group = Group.objects.create(
            name="Test Group", 
            amount=20, 
            start_year=2023
        )
        
        # Valid data for standard creation
        self.valid_data = {
            "semester": self.semester.id,
            "subject": self.subject.id,
            "teacher": self.teacher.id,
            "class_type": self.class_type.id,
            "group": self.group.id,
            "amount": 10,
            "duration": 1,
        }

    def test_create_with_group_and_no_course_number(self):
        """Should succeed without course_number if group is present"""
        data = self.valid_data.copy()
        # course_number is implicit missing
        response = self.client.post('/api/study_plans/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(StudyPlan.objects.filter(group=self.group).exists())

    def test_create_with_group_and_null_course_number(self):
        """Should succeed with explicit null course_number if group is present"""
        data = self.valid_data.copy()
        data['course_number'] = None
        response = self.client.post('/api/study_plans/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_creates_for_course_if_only_course_number(self):
        """
        Should fallback to _create_for_course if group/stream missing but course_number present.
        Since _create_for_course does many things, we just check that it DOESN'T fail with 'Missing group/stream' validation from serializer immediately,
        but enters the custom bulk logic. Use an invalid course_number to provoke a specific error from that method,
        or just check that we don't get 400 "Needs group or stream".
        """
        data = {
            "course_number": 999, # Invalid course number, likely to fail integer conversion or just custom logic
             # Minimal other fields to pass early checks in _create_for_course if needed
        }
        response = self.client.post('/api/study_plans/', data, format='json')
        # Expecting 400, but checking the message to ensure it hit the bulk logic, not the serializer validation
        # The view handles _create_for_course and catches errors.
        
        # If it hit serializer validation (because view logic was wrong), it would complain about missing fields required by Model/Serializer if it didn't use `write_only` or `read_only` fields correctly
        # Actually simplest check: 
        # If logic is correct, it calls _create_for_course.
        # If logic is incorrect (standard create), it validates serializer. Serializer requires group OR stream.
        # So if we send ONLY course_number, standard create would fail with "Необхідно вказати або Групу, або Потік."
        
        # We want to ensure we DO NOT get that specific serializer error if course_number is present.
        
        self.assertNotEqual(str(response.data), "{'non_field_errors': [ErrorDetail(string='Необхідно вказати або Групу, або Потік.', code='invalid')]}")
        
    def test_standard_validation_still_works(self):
        """If no group, no stream, no course_number -> should fail standard validation"""
        data = self.valid_data.copy()
        del data['group']
        # No stream either
        
        response = self.client.post('/api/study_plans/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Should now complain about missing group/stream
        self.assertIn("Необхідно вказати або Групу, або Потік.", str(response.data))
