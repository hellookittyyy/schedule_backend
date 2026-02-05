from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.core.exceptions import ValidationError
from api.models import StudyPlan, ClassType, Semester, Subject, Teacher
from api.serializers import StudyPlanSerializer, ClassTypeSerializer
from api.services.study_plan_service import StudyPlanBulkService

class ClassTypeViewSet(viewsets.ModelViewSet):
    queryset = ClassType.objects.all()
    serializer_class = ClassTypeSerializer

class StudyPlanViewSet(viewsets.ModelViewSet):
    queryset = StudyPlan.objects.all()
    serializer_class = StudyPlanSerializer
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    
    filterset_fields = ['semester', 'group', 'teacher', 'subject', 'stream']
    search_fields = ['group__name', 'subject__name', 'teacher__name']
    
    def create(self, request, *args, **kwargs):
        course_number = request.data.get('course_number')
        
        # Якщо є course_number - виконати масове створення
        if course_number is not None:
            return self._create_for_course(request, course_number)
        
        # Інакше - стандартне створення
        return super().create(request, *args, **kwargs)
    
    def _create_for_course(self, request, course_number):
        try:
            # Валідація та отримання обов'язкових полів
            try:
                course_number = int(course_number)
            except (ValueError, TypeError):
                return Response(
                    {"error": f"course_number має бути числом, отримано: {course_number}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Отримати обов'язкові об'єкти
            try:
                semester_id = request.data.get('semester')
                semester = Semester.objects.get(id=semester_id)
            except (ValueError, TypeError, Semester.DoesNotExist):
                return Response(
                    {"error": "Невірний або відсутній semester"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                subject_id = request.data.get('subject')
                subject = Subject.objects.get(id=subject_id)
            except (ValueError, TypeError, Subject.DoesNotExist):
                return Response(
                    {"error": "Невірний або відсутній subject"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                teacher_id = request.data.get('teacher')
                teacher = Teacher.objects.get(id=teacher_id)
            except (ValueError, TypeError, Teacher.DoesNotExist):
                return Response(
                    {"error": "Невірний або відсутній teacher"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                class_type_id = request.data.get('class_type')
                class_type = ClassType.objects.get(id=class_type_id)
            except (ValueError, TypeError, ClassType.DoesNotExist):
                return Response(
                    {"error": "Невірний або відсутній class_type"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Отримати кількість занять
            try:
                amount = int(request.data.get('amount', 0))
                if amount <= 0:
                    raise ValueError("amount має бути позитивним числом")
            except (ValueError, TypeError):
                return Response(
                    {"error": "Невірна кількість занять (amount)"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Отримати опціональні поля
            try:
                duration = int(request.data.get('duration', 1))
                if duration <= 0:
                    raise ValueError("duration має бути позитивним числом")
            except (ValueError, TypeError):
                return Response(
                    {"error": "Невірна тривалість (duration)"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            required_room_type = None
            if request.data.get('required_room_type'):
                try:
                    from api.models import RoomType
                    required_room_type = RoomType.objects.get(
                        id=request.data.get('required_room_type')
                    )
                except (ValueError, TypeError, RoomType.DoesNotExist):
                    return Response(
                        {"error": "Невірний required_room_type"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            constraints = request.data.get('constraints', {})
            
            # Виконати масове створення
            result = StudyPlanBulkService.create_study_plans_for_course(
                course_number=course_number,
                semester=semester,
                subject=subject,
                teacher=teacher,
                class_type=class_type,
                amount=amount,
                duration=duration,
                required_room_type=required_room_type,
                constraints=constraints
            )
            
            if result['success']:
                return Response(result, status=status.HTTP_201_CREATED)
            else:
                return Response(result, status=status.HTTP_400_BAD_REQUEST)
        
        except ValidationError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {"error": f"Помилка сервера: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='bulk-create-for-course')
    def bulk_create_for_course(self, request):
        return self._create_for_course(request, request.data.get('course_number'))