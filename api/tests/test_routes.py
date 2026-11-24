"""Перевіряє маршрути типів занять і порожній `semesters/current`."""

from rest_framework import status
from rest_framework.test import APITestCase

from api.models import Semester
from api.tests.factories import make_class_type


class ClassTypeRoutesTests(APITestCase):
    def setUp(self):
        self.class_type = make_class_type(name='Консультація')

    def test_snake_case_route_returns_seeded_and_created_types(self):
        response = self.client.get('/api/class_types/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertIsInstance(body, list)
        self.assertTrue(body)
        self.assertIn('Консультація', [item['name'] for item in body])

    def test_kebab_case_alias_returns_same_payload(self):
        snake = self.client.get('/api/class_types/')
        kebab = self.client.get('/api/class-types/')

        self.assertEqual(snake.status_code, status.HTTP_200_OK)
        self.assertEqual(kebab.status_code, status.HTTP_200_OK)
        self.assertEqual(kebab.json(), snake.json())


class SemesterCurrentEmptyTests(APITestCase):
    def test_current_semester_with_empty_db_is_json_404(self):
        self.assertFalse(Semester.objects.exists())

        response = self.client.get('/api/semesters/current/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('application/json', response['Content-Type'])
        self.assertNotIn('text/html', response['Content-Type'])
        self.assertIn('detail', response.json())
