from django.db import models

class Subject(models.Model):
    name = models.CharField(max_length=200, verbose_name="Назва предмету")
    description = models.TextField(blank=True, verbose_name="Опис")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Предмет"
        verbose_name_plural = "Предмети"