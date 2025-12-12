from django.db import models
from django.core.exceptions import ValidationError
from django.db.models import Q
from .schedule import Semester
from .groups import Group, Stream
from .subjects import Subject
from .teachers import Teacher
from .rooms import RoomType

class ClassType(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Тип заняття")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Тип заняття"
        verbose_name_plural = "Типи занять"


class StudyPlan(models.Model):
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, related_name='study_plans', verbose_name="Семестр")
    
    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name='study_plans', verbose_name="Група", null=True, blank=True)
    stream = models.ForeignKey(Stream, on_delete=models.PROTECT, related_name='study_plans', verbose_name="Потік", null=True, blank=True)
    
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='study_plans', verbose_name="Предмет")
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='study_plans', verbose_name="Викладач")
    class_type = models.ForeignKey(ClassType, on_delete=models.PROTECT, verbose_name="Тип заняття")
    
    required_room_type = models.ForeignKey(RoomType, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Необхідний тип аудиторії")
    duration = models.PositiveIntegerField(default=1, verbose_name="Тривалість (пар)", help_text="Duration in pairs")
    
    amount = models.PositiveIntegerField(verbose_name="Кількість занять", help_text="Скільки разів це заняття має відбутися за семестр")
    
    constraints = models.JSONField(default=dict, blank=True, verbose_name="Додаткові вимоги")

    @property
    def target_audience_size(self):
        """
        Повертає загальну кількість студентів, які мають бути присутні на занятті.
        """
        if self.group:
            return self.group.amount
        elif self.stream:
            return sum(group.amount for group in self.stream.groups.all())
        return 0

    def __str__(self):
        target = self.stream if self.stream else self.group
        return f"{target} - {self.subject} ({self.class_type})"

    def clean(self):
        super().clean()
        
        if self.group and self.stream:
            raise ValidationError("Не можна вказувати і Групу, і Потік одночасно. Оберіть щось одне.")
        
        if not self.group and not self.stream:
            raise ValidationError("Необхідно вказати або Групу, або Потік.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "План заняття"
        verbose_name_plural = "Навчальний план"
        
        unique_together = [
            ['semester', 'subject', 'class_type', 'teacher', 'group'],
            ['semester', 'subject', 'class_type', 'teacher', 'stream'],
        ]