from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend

from api.models import Teacher, Subject
from api.serializers import TeacherSerializer

class TeacherViewSet(viewsets.ModelViewSet):
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['name']
    filterset_fields = ['subjects']

    @action(detail=True, methods=['post'])
    def manage_subjects(self, request, pk=None):
        teacher = self.get_object()
        subject_id = request.data.get('subject_id')
        action_type = request.data.get('action')

        if not subject_id:
            return Response({"error": "subject_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        subject = get_object_or_404(Subject, id=subject_id)

        if action_type == 'add':
            teacher.subjects.add(subject)
            message = "Subject added"
        elif action_type == 'remove':
            teacher.subjects.remove(subject)
            message = "Subject removed"
        else:
            return Response({"error": "Invalid action. Use 'add' or 'remove'"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"status": message, "subjects": teacher.subjects.values_list('id', flat=True)})