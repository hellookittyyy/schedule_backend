from django.db import models

class Group(models.Model):
    name = models.CharField(max_length=150, verbose_name="Назва групи")
    amount = models.PositiveIntegerField(verbose_name="Кількість студентів")
    start_year = models.IntegerField(verbose_name="Рік початку навчання")

    def __str__(self):
        return f"{self.name} ({self.start_year})"
    
    class Meta:
        verbose_name = "Група"
        verbose_name_plural = "Групи"

class Stream(models.Model):
    name = models.CharField(max_length=150, verbose_name="Назва потоку")
    groups = models.ManyToManyField(Group, related_name='streams', verbose_name="Групи")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Потік"
        verbose_name_plural = "Потоки"