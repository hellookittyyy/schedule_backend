from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
import calendar
from datetime import timedelta, datetime

class Semester(models.Model):
    name = models.CharField(max_length=150, verbose_name="Назва семестру")
    start_date = models.DateField(verbose_name="Дата початку")
    end_date = models.DateField(verbose_name="Дата завершення")
    is_current = models.BooleanField(
        default=False, 
        verbose_name="Поточний семестр",
        help_text="Якщо відмічено, цей семестр буде використовуватися за замовчуванням."
    )
    
    configuration = models.JSONField(default=dict, verbose_name="Налаштування генерації", blank=True)

    def __str__(self):
        return f"{self.name} ({self.start_date} - {self.end_date})"

    def save(self, *args, **kwargs):
        if self.is_current:
            with transaction.atomic():
                Semester.objects.filter(is_current=True).exclude(pk=self.pk).update(is_current=False)
        
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Семестр"
        verbose_name_plural = "Семестри"
    
    def synchronize_slots(self):
        config = self.configuration or {}
        period_times = config.get('period_times', {
            "1": {"start": "08:30", "end": "09:50"},
            "2": {"start": "10:10", "end": "11:30"},
            "3": {"start": "11:50", "end": "13:10"},
            "4": {"start": "13:30", "end": "14:50"},
        })
        max_periods = config.get('max_periods_per_day', 4)
        exclude_days = config.get('exclude_days', [6, 7])

        valid_slot_ids = []
        current_date = self.start_date
        
        while current_date <= self.end_date:
            day_of_week = current_date.isoweekday()
            
            if day_of_week not in exclude_days:
                for p_num in range(1, max_periods + 1):
                    times = period_times.get(str(p_num), {"start": "00:00", "end": "00:00"})
                    
                    slot, _ = TimeSlot.objects.update_or_create(
                        semester=self,
                        date=current_date,
                        period_number=p_num,
                        defaults={
                            'start_time': times['start'],
                            'end_time': times['end'],
                        }
                    )
                    slot.save()
                    valid_slot_ids.append(slot.id)
            
            current_date += timedelta(days=1)

        TimeSlot.objects.filter(semester=self).exclude(id__in=valid_slot_ids).delete()


class TimeSlot(models.Model):
    class WeekType(models.TextChoices):
        FULL = 'FULL', _('Постійно')
        NUMERATOR = 'NUMERATOR', _('Чисельник')
        DENOMINATOR = 'DENOMINATOR', _('Знаменник')

    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, related_name='timeslots')
    date = models.DateField(verbose_name="Дата")
    
    period_number = models.PositiveIntegerField(default=1, verbose_name="Номер пари")
    week_type = models.CharField(
        max_length=20, 
        choices=WeekType.choices, 
        default=WeekType.FULL,
        verbose_name="Тип тижня"
    )
    day_of_week = models.IntegerField(verbose_name="День тижня (1-7)", default=1)
    
    start_time = models.TimeField(verbose_name="Час початку")
    end_time = models.TimeField(verbose_name="Час завершення")
    
    is_available = models.BooleanField(default=True, verbose_name="Доступний для планування")
    
    day_name = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"[{self.week_type}] {self.date} ({self.day_name}) | Пара {self.period_number}"

    @property
    def number_of_week_in_semester(self):
        """Calculates week number relative to semester start (1-based index)."""
        if not self.semester or not self.semester.start_date:
            return 1
        delta = self.date - self.semester.start_date
        return (delta.days // 7) + 1

    def save(self, *args, **kwargs):
        if self.date:
            self.day_name = self.date.strftime('%A')
            self.day_of_week = self.date.isoweekday()

            iso_week = self.date.isocalendar()[1]
            if iso_week % 2 != 0:
                self.week_type = self.WeekType.NUMERATOR
            else:
                self.week_type = self.WeekType.DENOMINATOR
        
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Часовий слот"
        verbose_name_plural = "Часові слоти"
        ordering = ['date', 'start_time']
        indexes = [
            models.Index(fields=['semester', 'week_type', 'day_of_week', 'period_number']),
        ]


class SemesterConstraint(models.Model):
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, related_name='constraints')
    teacher = models.ForeignKey('Teacher', on_delete=models.CASCADE, null=True, blank=True, related_name='semester_constraints')
    group = models.ForeignKey('Group', on_delete=models.CASCADE, null=True, blank=True, related_name='semester_constraints')
    stream = models.ForeignKey('Stream', on_delete=models.CASCADE, null=True, blank=True, related_name='semester_constraints')
    room = models.ForeignKey('Room', on_delete=models.CASCADE, null=True, blank=True, related_name='semester_constraints')
    configuration = models.JSONField(
        verbose_name="Конфігурація обмеження",
        help_text='Example: {"banned_days": [1, 5], "banned_periods": [4]}'
    )
    is_active = models.BooleanField(default=True, verbose_name="Активне")

    def __str__(self):
        entity = self.teacher or self.group or self.stream or self.room
        return f"Constraint for {entity} in {self.semester}"

    def clean(self):
        super().clean()
        
        entities = [self.teacher, self.group, self.stream, self.room]
        set_count = sum(1 for e in entities if e is not None)
        
        config_type = self.configuration.get('type')
        SPECIAL_TYPES = ['sequential_lessons']

        if set_count == 0:
            if config_type in SPECIAL_TYPES:
                return
            else:
                raise ValidationError("Необхідно вказати хоча б одну сутність (викладач, група, потік або аудиторію).")
        
        if set_count > 1:
            raise ValidationError("Можна вказати лише одну сутність.")

    class Meta:
        verbose_name = "Обмеження семестру"
        verbose_name_plural = "Обмеження семестрів"


class Lesson(models.Model):
    study_plan = models.ForeignKey('StudyPlan', on_delete=models.CASCADE, related_name='lessons')
    time_slot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE, related_name='lessons', null=True)
    room = models.ForeignKey('Room', on_delete=models.SET_NULL, null=True, blank=True, related_name='lessons')
    
    is_locked = models.BooleanField(default=False, verbose_name="Закріплено", help_text="Manually pinned by user")

    def __str__(self):
        return f"{self.study_plan} @ {self.time_slot} in {self.room or 'TBD'}"
    class Meta:
        verbose_name = "Заняття"
        verbose_name_plural = "Заняття"
        unique_together = [['room', 'time_slot']]
        indexes = [
            models.Index(fields=['time_slot', 'room']),
            models.Index(fields=['study_plan']),
        ]