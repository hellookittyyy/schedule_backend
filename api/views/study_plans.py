from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from api.models import StudyPlan, ClassType
from api.serializers import StudyPlanSerializer, ClassTypeSerializer

class ClassTypeViewSet(viewsets.ModelViewSet):
    queryset = ClassType.objects.all()
    serializer_class = ClassTypeSerializer

class StudyPlanViewSet(viewsets.ModelViewSet):
    queryset = StudyPlan.objects.all()
    serializer_class = StudyPlanSerializer
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    
    filterset_fields = ['semester', 'group', 'teacher', 'subject', 'stream']
    search_fields = ['group__name', 'subject__name', 'teacher__name']