from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Sum
from api.models import Teacher, Subject, Group, Room, Semester, Lesson, StudyPlan

class DashboardStatsView(APIView):
    def get(self, request):
        stats = {
            "teachers": Teacher.objects.count(),
            "subjects": Subject.objects.count(),
            "groups": Group.objects.count(),
            "rooms": Room.objects.count(),
            "semesters": Semester.objects.count(),
        }

        current_semester = Semester.objects.filter(is_current=True).first()
        
        if current_semester:
            scheduled_lessons = Lesson.objects.filter(study_plan__semester=current_semester).count()
            total_planned = StudyPlan.objects.filter(semester=current_semester).aggregate(Sum('amount'))['amount__sum'] or 0
            
            stats["classes_scheduled"] = scheduled_lessons
            stats["classes_planned"] = total_planned
            stats["weekly_load"] = int(total_planned / 16) if total_planned else 0
        else:
            stats["classes_scheduled"] = 0
            stats["classes_planned"] = 0
            stats["weekly_load"] = 0

        return Response(stats)