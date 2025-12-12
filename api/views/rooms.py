from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from api.models import Room, RoomType
from api.serializers import RoomSerializer, RoomTypeSerializer

class RoomTypeViewSet(viewsets.ModelViewSet):
    queryset = RoomType.objects.all()
    serializer_class = RoomTypeSerializer

class RoomViewSet(viewsets.ModelViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    
    # Пошук по назві аудиторії ТА назві типу
    search_fields = ['title', 'room_type__name']
    
    # Сортування (наприклад, по місткості)
    ordering_fields = ['capacity', 'title']