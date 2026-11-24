"""Protected deletes answer 409 JSON, and error bodies carry a machine code."""

from rest_framework.test import APITestCase

from api.models import ClassType, Group, RoomType, Stream
from api.tests.factories import (
    make_class_type,
    make_group,
    make_room,
    make_room_type,
    make_semester,
    make_stream,
    make_study_plan,
)


class ProtectedDeleteTests(APITestCase):
    def assert_json_409(self, response):
        self.assertEqual(response.status_code, 409, response.content)
        self.assertTrue(response["Content-Type"].startswith("application/json"))
        data = response.json()
        self.assertEqual(data["code"], "protected")
        self.assertTrue(data["detail"])
        return data

    def test_delete_room_type_in_use(self):
        room_type = make_room_type()
        make_room(room_type=room_type)

        data = self.assert_json_409(
            self.client.delete(f"/api/room_types/{room_type.pk}/")
        )

        self.assertEqual(data["blocked_by"], [{"model": "Аудиторії", "count": 1}])
        self.assertTrue(RoomType.objects.filter(pk=room_type.pk).exists())

    def test_delete_group_used_by_study_plan(self):
        group = make_group()
        make_study_plan(make_semester(), group=group, class_type=make_class_type(name="Семінар"))

        self.assert_json_409(self.client.delete(f"/api/groups/{group.pk}/"))

        self.assertTrue(Group.objects.filter(pk=group.pk).exists())

    def test_delete_stream_used_by_study_plan(self):
        stream = make_stream()
        make_study_plan(make_semester(), stream=stream, class_type=make_class_type(name="Семінар"))

        self.assert_json_409(self.client.delete(f"/api/streams/{stream.pk}/"))

        self.assertTrue(Stream.objects.filter(pk=stream.pk).exists())

    def test_delete_class_type_used_by_study_plan(self):
        class_type = make_class_type(name="Семінар")
        make_study_plan(make_semester(), class_type=class_type)

        self.assert_json_409(self.client.delete(f"/api/class_types/{class_type.pk}/"))

        self.assertTrue(ClassType.objects.filter(pk=class_type.pk).exists())

    def test_delete_unused_room_type(self):
        room_type = make_room_type()

        response = self.client.delete(f"/api/room_types/{room_type.pk}/")

        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(RoomType.objects.filter(pk=room_type.pk).exists())

    def test_not_found_has_code(self):
        response = self.client.get("/api/rooms/999999/")

        self.assertEqual(response.status_code, 404, response.content)
        self.assertTrue(response["Content-Type"].startswith("application/json"))
        self.assertEqual(response.json()["code"], "not_found")
