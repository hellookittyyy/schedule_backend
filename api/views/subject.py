from rest_framework import viewsets, filters
from api.models import Subject
from api.serializers import SubjectSerializer

class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']