from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from api.models import Semester, TimeSlot, SemesterConstraint, Lesson
from api.serializers import SemesterSerializer, TimeSlotSerializer, SemesterConstraintSerializer, LessonSerializer
from api.filters import LessonFilter

class SemesterViewSet(viewsets.ModelViewSet):
    queryset = Semester.objects.all()
    serializer_class = SemesterSerializer

    @action(detail=True, methods=['get'])
    def slots(self, request, pk=None):
        semester = self.get_object()
        slots = semester.timeslots.all()
        serializer = TimeSlotSerializer(slots, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def set_current(self, request, pk=None):
        semester = self.get_object()
        semester.is_current = True
        semester.save()
        return Response({'status': 'semester set as current', 'is_current': True})
    
    @action(detail=False, methods=['get'])
    def current(self, request):
        semester = Semester.objects.filter(is_current=True).first()
        if not semester:
            semester = Semester.objects.order_by('-start_date').first()
        
        if semester:
            serializer = self.get_serializer(semester)
            return Response(serializer.data)
        return Response({'detail': 'No semesters found'}, status=status.HTTP_404_NOT_FOUND)

class TimeSlotViewSet(viewsets.ModelViewSet):
    queryset = TimeSlot.objects.all()
    serializer_class = TimeSlotSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['semester', 'week_type', 'day_of_week', 'period_number', 'is_available']
    ordering_fields = ['date', 'start_time', 'period_number']

class SemesterConstraintViewSet(viewsets.ModelViewSet):
    queryset = SemesterConstraint.objects.all()
    serializer_class = SemesterConstraintSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['semester', 'teacher', 'group', 'stream', 'room', 'is_active']

class LessonViewSet(viewsets.ModelViewSet):
    queryset = Lesson.objects.all()
    serializer_class = LessonSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['study_plan', 'time_slot', 'room', 'is_locked']
    ordering_fields = ['time_slot__date', 'time_slot__start_time']
    filterset_class = LessonFilter