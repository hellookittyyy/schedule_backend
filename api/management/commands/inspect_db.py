from django.core.management.base import BaseCommand
from django.db.models import Count
# Імпортуйте ваші моделі. 
# Якщо у вас вони розкидані по файлах, імпортуйте їх звідти, 
# наприклад: from api.models.teachers import Teacher
from api.models import (
    Semester, RoomType, Room, Subject, Teacher, 
    Group, Stream, TimeSlot, StudyPlan, ClassType
)

class Command(BaseCommand):
    help = 'Inspect current database state (ReadOnly)'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('='*40))
        self.stdout.write(self.style.SUCCESS('      DATABASE INSPECTION REPORT      '))
        self.stdout.write(self.style.SUCCESS('='*40))

        # 1. SEMESTERS
        self.print_header(f"📅 SEMESTERS (Total: {Semester.objects.count()})")
        for s in Semester.objects.all():
            self.stdout.write(f"[ID: {s.id}] {s.name} ({s.start_date} - {s.end_date})")

        # 2. INFRASTRUCTURE (RoomTypes & Rooms)
        self.print_header(f"🏛️ ROOM TYPES (Total: {RoomType.objects.count()})")
        for rt in RoomType.objects.all():
            self.stdout.write(f"[ID: {rt.id}] {rt.name} (slug: {rt.slug})")

        self.print_header(f"🚪 ROOMS (Total: {Room.objects.count()})")
        for r in Room.objects.select_related('room_type').all():
            self.stdout.write(f"[ID: {r.id}] {r.title} | {r.room_type.name} | Cap: {r.capacity}")

        # 3. CLASS TYPES
        self.print_header(f"🏷️ CLASS TYPES (Total: {ClassType.objects.count()})")
        for ct in ClassType.objects.all():
            self.stdout.write(f"[ID: {ct.id}] {ct.name}")

        # 4. ACADEMIC ENTITIES
        self.print_header(f"📖 SUBJECTS (Total: {Subject.objects.count()})")
        for s in Subject.objects.all()[:10]: # Show first 10
            self.stdout.write(f"[ID: {s.id}] {s.name}")
        if Subject.objects.count() > 10:
            self.stdout.write("... and more")

        self.print_header(f"👨‍🏫 TEACHERS (Total: {Teacher.objects.count()})")
        for t in Teacher.objects.prefetch_related('subjects').all()[:10]:
            subjects = ", ".join([s.name for s in t.subjects.all()[:3]])
            self.stdout.write(f"[ID: {t.id}] {t.name} -> Subs: {subjects}...")

        self.print_header(f"👥 GROUPS (Total: {Group.objects.count()})")
        for g in Group.objects.all()[:10]:
            self.stdout.write(f"[ID: {g.id}] {g.name} (Studs: {g.amount})")

        self.print_header(f"🌊 STREAMS (Total: {Stream.objects.count()})")
        for st in Stream.objects.prefetch_related('groups').all():
            g_names = ", ".join([g.name for g in st.groups.all()])
            self.stdout.write(f"[ID: {st.id}] {st.name} -> [{g_names}]")

        # 5. GENERATION DATA
        self.print_header("⚙️ GENERATION DATA")
        
        # TimeSlots stats
        slots_count = TimeSlot.objects.count()
        self.stdout.write(f"⏱️ TimeSlots Total: {slots_count}")
        if slots_count > 0:
            by_sem = TimeSlot.objects.values('semester__name').annotate(total=Count('id'))
            for entry in by_sem:
                self.stdout.write(f"   - {entry['semester__name']}: {entry['total']} slots")

        # StudyPlans stats
        plans_count = StudyPlan.objects.count()
        self.stdout.write(f"\n📑 StudyPlans Total: {plans_count}")
        if plans_count > 0:
            by_sem = StudyPlan.objects.values('semester__name').annotate(total=Count('id'))
            for entry in by_sem:
                self.stdout.write(f"   - {entry['semester__name']}: {entry['total']} plans")

        self.stdout.write("\n" + "="*40 + "\n")

    def print_header(self, text):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n--- {text} ---"))