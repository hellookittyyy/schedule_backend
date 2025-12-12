from django.core.management.base import BaseCommand
from api.models.schedule import TimeSlot  # Зміни шлях, якщо модель в іншому файлі
from datetime import time

class Command(BaseCommand):
    help = 'Fixes day_of_week and period_number in TimeSlots based on date and start_time'

    def handle(self, *args, **kwargs):
        slots = TimeSlot.objects.all()
        count = 0
        
        # Налаштування часу початку пар (підстав свій розклад дзвінків)
        PERIOD_MAP = {
            time(8, 30): 1,
            time(10, 10): 2,
            time(11, 50): 3,
            time(13, 30): 4,
            time(15, 00): 5, # або 15:05
            time(16, 30): 6, # або 16:40
            time(18, 00): 7,
            time(19, 30): 8,
        }

        self.stdout.write("Починаємо виправлення слотів...")

        for slot in slots:
            needs_save = False

            # 1. Виправляємо день тижня на основі дати
            # weekday(): 0=Monday, 6=Sunday. Нам треба 1=Monday.
            correct_day = slot.date.weekday() + 1
            
            if slot.day_of_week != correct_day:
                slot.day_of_week = correct_day
                needs_save = True

            # 2. Виправляємо номер пари на основі часу
            # Шукаємо точний збіг часу
            correct_period = PERIOD_MAP.get(slot.start_time)
            
            # Якщо точного збігу немає, спробуємо знайти "схожий" (в межах години)
            if not correct_period:
                for t, p in PERIOD_MAP.items():
                    if t.hour == slot.start_time.hour:
                        correct_period = p
                        break
            
            if correct_period and slot.period_number != correct_period:
                slot.period_number = correct_period
                needs_save = True

            if needs_save:
                slot.save()
                count += 1

        self.stdout.write(self.style.SUCCESS(f'Успішно виправлено {count} слотів!'))