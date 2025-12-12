from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    GroupViewSet, StreamViewSet, SubjectViewSet, TeacherViewSet, 
    RoomViewSet, RoomTypeViewSet, SemesterViewSet, TimeSlotViewSet, 
    ClassTypeViewSet, StudyPlanViewSet, SemesterConstraintViewSet, LessonViewSet
)
from api.views.generation import GenerateScheduleView
from api.views.dashboard import DashboardStatsView

router = DefaultRouter()
router.register(r'groups', GroupViewSet, basename='group')
router.register(r'streams', StreamViewSet, basename='stream')
router.register(r'subjects', SubjectViewSet, basename='subject')
router.register(r'teachers', TeacherViewSet, basename='teacher')
router.register(r'rooms', RoomViewSet, basename='room')
router.register(r'room_types', RoomTypeViewSet, basename='room_type')
router.register(r'semesters', SemesterViewSet, basename='semester')
router.register(r'timeslots', TimeSlotViewSet, basename='timeslot')
router.register(r'class-types', ClassTypeViewSet, basename='classtype')
router.register(r'study_plans', StudyPlanViewSet, basename='studyplan')
router.register(r'semester_constraints', SemesterConstraintViewSet, basename='semesterconstraint')
router.register(r'lessons', LessonViewSet, basename='lesson')


urlpatterns = [
    path('', include(router.urls)),
    path('generate-schedule/', GenerateScheduleView.as_view(), name='generate-schedule'),
    path('stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
]