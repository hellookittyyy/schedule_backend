import django_filters
from django.utils import timezone
from .models import Lesson

class LessonFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name='time_slot__date', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='time_slot__date', lookup_expr='lte')
    
    teacher_name = django_filters.CharFilter(field_name='study_plan__teacher__name', lookup_expr='icontains')
    group_name = django_filters.CharFilter(field_name='study_plan__group__name', lookup_expr='icontains')
    group_id = django_filters.NumberFilter(field_name='study_plan__group__id')
    
    semester = django_filters.NumberFilter(field_name='study_plan__semester')
    study_plan__semester = django_filters.NumberFilter(field_name='study_plan__semester')

    course = django_filters.NumberFilter(method='filter_by_course')

    class Meta:
        model = Lesson
        fields = ['study_plan', 'room', 'is_locked']

    def filter_by_course(self, queryset, name, value):
        """
        Фільтрує групи за курсом, вираховуючи рік вступу.
        """
        try:
            course_num = int(value)
            now = timezone.now()
            current_year = now.year
            current_month = now.month

            if current_month >= 8:
                academic_year_start = current_year
            else:
                academic_year_start = current_year - 1

            target_start_year = academic_year_start - (course_num - 1)

            return queryset.filter(study_plan__group__start_year=target_start_year)
        
        except ValueError:
            return queryset