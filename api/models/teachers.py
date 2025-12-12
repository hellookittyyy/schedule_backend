from django.db import models
from .subjects import Subject

class Teacher(models.Model):
    name = models.CharField(max_length=150, verbose_name="ПІБ Викладача")
    subjects = models.ManyToManyField(Subject, related_name='teachers', blank=True, verbose_name="Предмети")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Викладач"
        verbose_name_plural = "Викладачі"