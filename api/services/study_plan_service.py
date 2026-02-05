from datetime import datetime
from django.db import transaction
from django.core.exceptions import ValidationError
from api.models import Group, StudyPlan


class StudyPlanBulkService:
    @staticmethod
    def get_start_year_for_course(course_number: int) -> int:
        if not isinstance(course_number, int) or course_number < 1 or course_number > 6:
            raise ValidationError(f"Номер курсу має бути від 1 до 6, отримано: {course_number}")
        
        today = datetime.now().date()
        current_year = today.year
        
        if today.month >= 8:
            academic_year_start = current_year
        else:
            academic_year_start = current_year - 1
        
        start_year = academic_year_start - (course_number - 1)
        
        return start_year
    
    @staticmethod
    def get_groups_for_course(course_number: int):
        start_year = StudyPlanBulkService.get_start_year_for_course(course_number)
        return Group.objects.filter(start_year=start_year).order_by('name')
    
    @staticmethod
    @transaction.atomic
    def create_study_plans_for_course(
        course_number: int,
        semester,
        subject,
        teacher,
        class_type,
        amount: int,
        duration: int = 1,
        required_room_type=None,
        constraints=None
    ):

        try:
            # Валідація вхідних даних
            if not isinstance(amount, int) or amount <= 0:
                raise ValidationError(f"Кількість занять має бути позитивним числом, отримано: {amount}")
            
            if not isinstance(duration, int) or duration <= 0:
                raise ValidationError(f"Тривалість має бути позитивним числом, отримано: {duration}")
            
            # Отримати групи для курсу
            groups = StudyPlanBulkService.get_groups_for_course(course_number)
            
            if not groups.exists():
                return {
                    "success": False,
                    "created_count": 0,
                    "skipped_count": 0,
                    "groups": [],
                    "skipped_groups": [],
                    "message": f"Не знайдено груп для курсу {course_number}",
                    "error": None
                }
            
            created_plans = []
            skipped_plans = []
            
            # Створити StudyPlan для кожної групи
            for group in groups:
                # Перевірити, чи вже існує такий план
                exists = StudyPlan.objects.filter(
                    semester=semester,
                    group=group,
                    subject=subject,
                    teacher=teacher,
                    class_type=class_type
                ).exists()
                
                if exists:
                    skipped_plans.append(group.name)
                    continue
                
                # Створити новий план
                study_plan = StudyPlan.objects.create(
                    semester=semester,
                    group=group,
                    stream=None,  # Явно встановити None для групи
                    subject=subject,
                    teacher=teacher,
                    class_type=class_type,
                    required_room_type=required_room_type,
                    duration=duration,
                    amount=amount,
                    constraints=constraints or {}
                )
                created_plans.append(study_plan)
            
            created_group_names = [p.group.name for p in created_plans]
            
            return {
                "success": True,
                "created_count": len(created_plans),
                "skipped_count": len(skipped_plans),
                "groups": created_group_names,
                "skipped_groups": skipped_plans,
                "message": f"Успішно створено {len(created_plans)} навчальних планів для курсу {course_number}",
                "error": None,
                "created_plans": [p.id for p in created_plans]
            }
        
        except ValidationError as e:
            return {
                "success": False,
                "created_count": 0,
                "skipped_count": 0,
                "groups": [],
                "skipped_groups": [],
                "message": None,
                "error": str(e)
            }
        except Exception as e:
            return {
                "success": False,
                "created_count": 0,
                "skipped_count": 0,
                "groups": [],
                "skipped_groups": [],
                "message": None,
                "error": f"Помилка при створенні планів: {str(e)}"
            }
