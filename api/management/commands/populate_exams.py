import random
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from api.models import (
    Teacher, Subject, Group, Room, RoomType, Stream,
    Semester, StudyPlan, ClassType, TimeSlot
)

class Command(BaseCommand):
    help = 'Populate database with EXAM session data'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("--- Генерація даних ЕКЗАМЕНАЦІЙНОЇ СЕСІЇ ---"))
        
        # 1. Отримуємо контекст (Семестр #7)
        try:
            # З вашого inspect_db ми бачимо, що ID 7 - це сесія
            semester = Semester.objects.get(id=7) 
            self.stdout.write(f"Обрано семестр: {semester.name} ({semester.start_date} - {semester.end_date})")
        except Semester.DoesNotExist:
            self.stdout.write(self.style.ERROR("Семестр ID=7 (Сесія) не знайдено!"))
            return

        # Тип заняття: Екзамен (ID 5)
        try:
            ct_exam = ClassType.objects.get(id=5)
        except ClassType.DoesNotExist:
            ct_exam = ClassType.objects.get_or_create(name="Екзамен")[0]

        # Типи кімнат
        rt_lecture = RoomType.objects.get(id=2) # Лекційна (для потокових екзаменів)
        rt_general = RoomType.objects.get(id=3) # Загальна (для груп)

        confirm = input(f"Згенерувати слоти та плани для '{semester.name}'? (y/n): ")
        if confirm.lower() != 'y': return

        with transaction.atomic():
            self.generate_slots(semester)
            self.generate_exam_plans(semester, ct_exam, rt_lecture, rt_general)
            
        self.stdout.write(self.style.SUCCESS("\n✅ Дані для сесії успішно створено!"))

    def generate_slots(self, semester):
        """
        Генерує слоти на 5 днів (Пн-Пт) сесії.
        Для екзаменів зазвичай використовують менше пар (наприклад, 1, 2, 3), бо вони довгі.
        """
        self.stdout.write("Перевірка часових слотів...")
        
        if TimeSlot.objects.filter(semester=semester).exists():
            self.stdout.write("  Слоти вже існують. Пропускаємо.")
            return

        # Генеруємо на 1 тиждень (дати з семестру)
        # 2025-12-15 (Понеділок) -> 2025-12-19 (П'ятниця)
        current_date = semester.start_date
        end_date = semester.end_date
        
        count = 0
        while current_date <= end_date:
            # 1=Mon, 7=Sun. Пропускаємо вихідні, якщо треба
            day_of_week = current_date.isoweekday()
            
            if day_of_week <= 5: # Тільки будні
                # Створюємо 3 слоти на день (Екзамени зазвичай зранку, в обід або ввечері)
                for period in range(1, 4): 
                    TimeSlot.objects.create(
                        semester=semester,
                        date=current_date,
                        day_of_week=day_of_week,
                        period_number=period,
                        week_type=0, # 0 = Неважливо (Сесія коротка)
                        start_time=self.get_start_time(period),
                        end_time=self.get_end_time(period)
                    )
                    count += 1
            
            current_date += timedelta(days=1)
            
        self.stdout.write(f"  Створено {count} слотів.")

    def generate_exam_plans(self, semester, ct_exam, rt_lec, rt_gen):
        """
        Створює StudyPlan по 1 екзамену на предмет.
        """
        self.stdout.write("Генерація планів екзаменів...")
        
        streams = Stream.objects.all()
        groups = Group.objects.all()
        subjects = list(Subject.objects.all())
        teachers = list(Teacher.objects.all())

        # 1. ПОТОКОВІ ЕКЗАМЕНИ (Складніші)
        # Якщо є предмет "Вища математика", ставимо екзамен на весь потік
        target_subject = next((s for s in subjects if "математика" in s.name.lower()), subjects[0])
        
        for stream in streams:
            # Знаходимо викладача
            teacher = self.get_teacher(target_subject, teachers)
            
            StudyPlan.objects.get_or_create(
                semester=semester,
                stream=stream, # Екзамен для всього потоку разом
                subject=target_subject,
                class_type=ct_exam,
                defaults={
                    "teacher": teacher,
                    "amount": 1, # Тільки 1 екзамен
                    "duration": 1, # Займає 1 слот (або можна ставити 2, якщо довгий)
                    "required_room_type": rt_lec # Потрібна велика аудиторія
                }
            )
            self.stdout.write(f"  [Stream] Екзамен: {target_subject.name} -> {stream.name}")

        # 2. ГРУПОВІ ЕКЗАМЕНИ
        # Для кожної групи беремо 3 випадкових предмета (окрім того, що був у потоці)
        for group in groups:
            group_subjects = random.sample([s for s in subjects if s != target_subject], k=3)
            
            for subj in group_subjects:
                teacher = self.get_teacher(subj, teachers)
                
                StudyPlan.objects.get_or_create(
                    semester=semester,
                    group=group,
                    subject=subj,
                    class_type=ct_exam,
                    defaults={
                        "teacher": teacher,
                        "amount": 1,
                        "duration": 1,
                        "required_room_type": rt_gen # Звичайна аудиторія
                    }
                )
        self.stdout.write(f"  Створено екзамени для {len(groups)} груп.")

    def get_teacher(self, subject, all_teachers):
        qualified = [t for t in all_teachers if subject in t.subjects.all()]
        if qualified: return random.choice(qualified)
        t = random.choice(all_teachers)
        t.subjects.add(subject)
        return t

    def get_start_time(self, period):
        times = {1: "09:00", 2: "13:00", 3: "16:00"}
        return times.get(period, "09:00")

    def get_end_time(self, period):
        times = {1: "12:00", 2: "15:00", 3: "19:00"}
        return times.get(period, "12:00")