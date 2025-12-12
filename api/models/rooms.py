from django.db import models

class RoomType(models.Model):
    name = models.CharField(max_length=100, verbose_name="Назва типу")
    description = models.CharField(max_length=255, blank=True, verbose_name="Короткий опис")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Тип аудиторії"
        verbose_name_plural = "Типи аудиторій"


class Room(models.Model):
    title = models.CharField(max_length=50, verbose_name="Назва/Номер аудиторії")
    building = models.CharField(max_length=50, verbose_name="Корпус")
    capacity = models.PositiveIntegerField(verbose_name="Місткість")
    
    room_type = models.ForeignKey(
        RoomType, 
        on_delete=models.PROTECT, 
        related_name='rooms',
        verbose_name="Тип аудиторії"
    )
    
    note = models.TextField(blank=True, verbose_name="Примітка")

    def __str__(self):
        return f"{self.title} ({self.building})"

    class Meta:
        verbose_name = "Аудиторія"
        verbose_name_plural = "Аудиторії"