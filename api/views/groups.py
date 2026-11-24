from rest_framework import viewsets, filters
from rest_framework.exceptions import ValidationError
from django.utils import timezone
from api.models import Group, Stream
from api.serializers import GroupSerializer, StreamSerializer

class GroupViewSet(viewsets.ModelViewSet):
    serializer_class = GroupSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']

    def get_queryset(self):
        """
        Перевизначаємо метод отримання даних, щоб додати кастомну логіку фільтрації.
        """
        queryset = Group.objects.all()
        
        course_param = self.request.query_params.get('course')
        
        if course_param:
            try:
                target_course = int(course_param)
                if not (1 <= target_course <= 6):
                    raise ValidationError("Курс має бути від 1 до 6")

                today = timezone.now().date()
                current_year = today.year
                current_month = today.month

                if current_month >= 8:
                    academic_year_start = current_year
                else:
                    academic_year_start = current_year - 1
                
                target_start_year = academic_year_start - (target_course - 1)
                
                queryset = queryset.filter(start_year=target_start_year)

            except ValueError:
                raise ValidationError("Параметр course має бути числом")

        return queryset

class StreamViewSet(viewsets.ModelViewSet):
    queryset = Stream.objects.all()
    serializer_class = StreamSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']
