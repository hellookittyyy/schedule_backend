import random
from django.core.management.base import BaseCommand
from django.db import transaction
from api.models import (
    Teacher, Subject, Group, Room, RoomType, Stream,
    Semester, StudyPlan, ClassType
)

class Command(BaseCommand):
    help = 'Add random test data on top of existing structure'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("Цей скрипт додасть дані до існуючих. Дублікати будуть пропущені."))
        confirm = input("Продовжити? (y/n): ")
        
        if confirm.lower() != 'y':
            return

        with transaction.atomic():
            self.generate_data()
            
        self.stdout.write(self.style.SUCCESS("\n✅ База даних успішно наповнена!"))

    def generate_data(self):
        # --- 1. ОТРИМАННЯ ІСНУЮЧИХ КОНТЕКСТІВ ---
        try:
            semester = Semester.objects.get(id=6) # 1 семестр 2025/2026
            self.stdout.write(f"Використовуємо семестр: {semester.name}")
        except Semester.DoesNotExist:
            self.stdout.write(self.style.ERROR("Семестр ID=6 не знайдено! Спочатку запустіть міграції або створіть семестр."))
            return

        # Типи кімнат
        rt_lab = RoomType.objects.get(id=1)   # Lab PC
        rt_lec = RoomType.objects.get(id=2)   # Lecture
        rt_gen = RoomType.objects.get(id=3)   # General

        # Типи занять
        ct_lecture = ClassType.objects.get(id=1)
        # Спробуємо знайти Лабораторну, якщо ні - беремо ID 3
        ct_lab = ClassType.objects.filter(name__icontains="Лабораторна").first() or ClassType.objects.get(id=3)
        ct_practice = ClassType.objects.get_or_create(name="Практична")[0] # Створимо, якщо немає

        # Існуючі сутності
        stream_fei = Stream.objects.get(id=1)
        groups_fei = list(stream_fei.groups.all()) # [ФЕІ-21, ФЕІ-22, ФЕІ-23]
        group_kn = Group.objects.get(id=2)         # КН-2025-1

        # --- 2. ДОДАВАННЯ НОВИХ ПРЕДМЕТІВ ТА ВИКЛАДАЧІВ ---
        
        new_subjects_data = [
            "Філософія", "Англійська мова (IT)", "Комп'ютерні мережі", 
            "Бази даних", "Операційні системи", "Кібербезпека"
        ]
        
        created_subjects = []
        for name in new_subjects_data:
            s, _ = Subject.objects.get_or_create(name=name)
            created_subjects.append(s)
            
        # Додаємо існуючі
        existing_subjects = list(Subject.objects.all())
        all_subjects = list(set(existing_subjects + created_subjects))

        new_teachers_names = [
            "Шевченко Тарас Григорович", "Франко Іван Якович", 
            "Леся Українка", "Сковорода Григорій Савич", "Костенко Ліна Василівна"
        ]

        all_teachers = list(Teacher.objects.all())
        
        for name in new_teachers_names:
            t, created = Teacher.objects.get_or_create(name=name)
            if created:
                # Даємо випадкові предмети
                t.subjects.set(random.sample(all_subjects, k=random.randint(2, 4)))
                all_teachers.append(t)
                self.stdout.write(f"Створено викладача: {t.name}")

        # --- 3. ДОДАВАННЯ АУДИТОРІЙ (Щоб уникнути Bottle-neck) ---
        # У вас всього 4 аудиторії, це дуже мало для 4 груп. Додамо ще 3.
        extra_rooms = [
            ("201", "Main", 40, rt_gen),
            ("202", "Main", 40, rt_gen),
            ("205", "Lab Corps", 25, rt_lab)
        ]
        for num, build, cap, rtype in extra_rooms:
            Room.objects.get_or_create(title=num, defaults={"building": build, "capacity": cap, "room_type": rtype})

        # --- 4. ГЕНЕРАЦІЯ STUDY PLANS ---
        self.stdout.write("Генерація навчальних планів...")

        # A. Плани для ПОТОКУ ФЕІ (Лекції)
        # Обираємо 3 предмети для спільних лекцій
        lecture_subjects = random.sample(all_subjects, k=3)
        
        for subj in lecture_subjects:
            # Знаходимо викладача
            teacher = self.get_teacher_for_subject(subj, all_teachers)
            if not teacher: continue

            # Створюємо лекцію для потоку
            sp, created = StudyPlan.objects.get_or_create(
                semester=semester,
                stream=stream_fei,
                subject=subj,
                class_type=ct_lecture,
                defaults={
                    "teacher": teacher,
                    "amount": 8, # 1 раз на 2 тижні (блимаюча) або 15 (щотижня)
                    "duration": 1,
                    "required_room_type": rt_lec
                }
            )
            if created:
                self.stdout.write(f"  [Stream] Лекція: {subj.name} -> {stream_fei.name}")

            # B. Плани для ГРУП ФЕІ (Практики/Лаби по цих же предметах)
            # Для кожної групи окремо
            for group in groups_fei:
                # 50% шанс що це Лаба (потрібен комп), 50% що Практика (звичайна)
                is_lab = random.choice([True, False])
                ctype = ct_lab if is_lab else ct_practice
                rtype = rt_lab if is_lab else rt_gen
                duration = 2 if is_lab else 1 # Лаби часто парами
                
                sp, created = StudyPlan.objects.get_or_create(
                    semester=semester,
                    group=group,
                    subject=subj,
                    class_type=ctype,
                    defaults={
                        "teacher": teacher, # Той самий викладач веде і практику
                        "amount": 15, # Щотижня
                        "duration": duration,
                        "required_room_type": rtype
                    }
                )

        # C. Плани для КН-2025-1 (Окремий світ)
        # Даємо їм 5 своїх предметів
        kn_subjects = random.sample(all_subjects, k=5)
        for subj in kn_subjects:
            teacher = self.get_teacher_for_subject(subj, all_teachers)
            if not teacher: continue

            # Лекція (тільки для групи, бо немає потоку)
            StudyPlan.objects.get_or_create(
                semester=semester,
                group=group_kn,
                subject=subj,
                class_type=ct_lecture,
                defaults={
                    "teacher": teacher,
                    "amount": 15,
                    "required_room_type": rt_gen # Лекція в звичайному класі, бо група мала
                }
            )
            
            # Практика
            StudyPlan.objects.get_or_create(
                semester=semester,
                group=group_kn,
                subject=subj,
                class_type=ct_practice,
                defaults={
                    "teacher": teacher,
                    "amount": 15,
                    "required_room_type": rt_gen
                }
            )
            
    def get_teacher_for_subject(self, subject, all_teachers):
        # Шукаємо хто може читати, або беремо першого ліпшого і довчаємо його
        qualified = [t for t in all_teachers if subject in t.subjects.all()]
        if qualified:
            return random.choice(qualified)
        
        # Якщо ніхто не знає предмету - навчимо випадкового
        t = random.choice(all_teachers)
        t.subjects.add(subject)
        return t