import logging
from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.db.models import Q, Prefetch

from api.models import (
    StudyPlan,
    Lesson,
    TimeSlot,
    Room,
    Semester,
    SemesterConstraint
)

logger = logging.getLogger("schedule_generator")
logger.setLevel(logging.INFO)

class ScheduleGenerator:
    def __init__(self, semester_id: int):
        self.semester = Semester.objects.get(id=semester_id)
        
        self.constraints = list(
            SemesterConstraint.objects.filter(
                semester=self.semester, 
                is_active=True
            ).select_related("group", "teacher", "stream")
        )

        self.memory_schedule = defaultdict(list)
        self.logs = []
        self.plans_map = {}
        self.locked_counts = defaultdict(int)
        self.time_slots_cache = {}  # Кеш таймслотів для швидшого доступу
        self.day_load = defaultdict(int) 
        self.daily_limit = 100 # Default safe value

    def log(self, message):
        print(message)
        logger.info(message)
        self.logs.append(message)

    @transaction.atomic
    def generate(self):
        try:
            self.log(f"Starting generation for: {self.semester.name}")

            Lesson.objects.filter(study_plan__semester=self.semester, is_locked=False).delete()
            self.load_locked_lessons_to_memory()

            plans = list(
                StudyPlan.objects.filter(semester=self.semester)
                .select_related("group", "stream", "teacher", "subject", "class_type")
                .prefetch_related("stream__groups") 
            )
            self.plans_map = {p.id: p for p in plans}

            # Враховуємо вже закріплені(locked) пари — зменшуємо кількість для планів
            for p in plans:
                locked = self.locked_counts.get(p.id, 0)
                if locked:
                    try:
                        original_amount = p.amount
                        p.amount = max(0, p.amount - locked)
                        self.log(f"Adjusted plan {p.id} amount: {original_amount} -> {p.amount} due to {locked} locked lessons")
                    except Exception:
                        pass

            # Фільтруємо плани, у яких вже немає уроків для розміщення
            plans = [p for p in plans if getattr(p, 'amount', 0) > 0]
            self.plans_map = {p.id: p for p in plans}

            if not plans:
                return {"success": False, "error": "No study plans found"}

            sorted_plans = self.sort_plans(plans)

            time_slots = list(TimeSlot.objects.filter(
                semester=self.semester, is_available=True
            ).order_by("date", "period_number"))
            
            # Заповнюємо кеш таймслотів
            self.time_slots_cache = {ts.id: ts for ts in time_slots}
            
            if not time_slots:
                return {"success": False, "error": "No time slots found"}

            created_count = 0
            unassigned_count = 0
            max_iterations = 0
            
            if not sorted_plans:
                 max_iterations = 0
            else:
                 max_iterations = max(p.amount for p in sorted_plans)

            total_lessons = sum(max(1, p.amount) for p in sorted_plans)
            unique_dates = {ts.date for ts in time_slots}
            total_days_slots = len(unique_dates) if unique_dates else 1
            
            import math
            self.daily_limit = math.ceil(total_lessons / total_days_slots)
            self.log(f"Daily balance limit set to: {self.daily_limit} (Lessons: {total_lessons}, Days: {total_days_slots})")

            for i in range(max_iterations):
                for plan in sorted_plans:
                    if i >= plan.amount:
                        continue

                    target_name = plan.group.name if plan.group else (plan.stream.name if plan.stream else "Unknown")

                    try:
                        slot = None
                        room = None
                        
                        with transaction.atomic():
                            # 1. First Pass: Strict Limit
                            slot, room = self.find_and_assign_slot(plan, time_slots, check_limit=True)

                            # 2. Soft Fallback: Ignore Limit if failed
                            if not slot:
                                 # Optional logger for debug
                                 # self.log(f"Fallback for {plan.id} lesson {i+1}")
                                 slot, room = self.find_and_assign_slot(plan, time_slots, check_limit=False)
                            
                            if slot and room:
                                Lesson.objects.create(study_plan=plan, time_slot=slot, room=room)
                                self.register_memory(plan, slot, room)
                                created_count += 1
                            else:
                                Lesson.objects.create(
                                    study_plan=plan, 
                                    time_slot=None, 
                                    room=None,
                                    is_locked=False
                                )
                                self.log(f"Warning: No slot found for {target_name} (lesson {i+1}). Added to Unassigned.")
                                unassigned_count += 1
                    except Exception as e:
                        self.log(f"Error processing lesson: {str(e)}")
                        try:
                            Lesson.objects.create(
                                study_plan=plan, 
                                time_slot=None, 
                                room=None,
                                is_locked=False
                            )
                            unassigned_count += 1
                        except:
                            pass

            status_msg = "completed successfully" if unassigned_count == 0 else f"completed with {unassigned_count} unassigned lessons"
            self.log(f"Generation {status_msg}. Created: {created_count}")

            return {
                "success": True,
                "created": created_count,
                "unassigned": unassigned_count,
                "logs": self.logs,
                "message": status_msg
            }

        except Exception as e:
            return {
                "success": False, 
                "created": 0, 
                "unassigned": 0, 
                "logs": self.logs, 
                "error": str(e)
            }

    def load_locked_lessons_to_memory(self):
        locked = Lesson.objects.filter(study_plan__semester=self.semester, is_locked=True)
        for l in locked:
            self.register_memory(l.study_plan, l.time_slot, l.room)
            try:
                self.locked_counts[l.study_plan.id] += 1
            except Exception:
                pass

    def register_memory(self, plan, slot, room):
        self.memory_schedule[slot.id].append({
            "plan_id": plan.id,
            "teacher_id": plan.teacher_id,
            "group_id": plan.group_id,
            "stream_id": plan.stream_id,
            "room_id": room.id if room else None,
            "stream_group_ids": [g.id for g in plan.stream.groups.all()] if plan.stream else []
        })
        self.day_load[slot.date] += 1 # Increment daily load

    def sort_plans(self, plans):
        leaders_ids = set()
        followers_ids = set()

        for c in self.constraints:
            cfg = c.configuration
            if cfg.get("type") == "sequential_lessons":
                val = cfg.get("value", {})
                if "leader_plan_id" in val:
                    leaders_ids.add(val["leader_plan_id"])
                if "follower_plan_id" in val:
                    followers_ids.add(val["follower_plan_id"])

        def sort_key(plan):
            is_leader = plan.id in leaders_ids
            is_follower = plan.id in followers_ids
            is_chained = is_leader or is_follower
            
            priority_group = 2
            if is_chained:
                priority_group = 0 if is_leader else 1
            
            is_stream = 0 if plan.stream else 1
            is_room_req = 0 if plan.required_room_type else 1
            
            return (priority_group, is_stream, is_room_req, -plan.amount)

        return sorted(plans, key=sort_key)

    def find_and_assign_slot(self, plan, time_slots, check_limit=True):
        print(f"DEBUG: Plan ID={plan.id}, Type='{plan.class_type.name}'")
        is_current_plan_exam = "екзамен" in plan.class_type.name.lower() or "exam" in plan.class_type.name.lower()
        
        follower_config = self.get_follower_config(plan.id)

        # Retrieve last assigned date for this plan, if any
        last_date = None
        for slot_id, items in self.memory_schedule.items():
            for item in items:
                if item["plan_id"] == plan.id:
                    slot_from_cache = self.time_slots_cache.get(slot_id)
                    if slot_from_cache:
                        if last_date is None or slot_from_cache.date > last_date:
                            last_date = slot_from_cache.date

        for idx, slot in enumerate(time_slots):
            # Daily Limit Check
            if check_limit and self.day_load[slot.date] >= self.daily_limit:
                continue

            if is_current_plan_exam:
                if not self.check_exam_day_limit(plan, slot):
                    continue

            if not self.check_dynamic_constraints(plan, slot): continue
            if not self.check_availability(plan, slot): continue
            if not self.check_sequential(plan, slot): continue

            room = self.find_free_room(plan, slot)
            if not room: continue

            return slot, room

        return None, None

    def get_follower_config(self, plan_id):
        for c in self.constraints:
            cfg = c.configuration
            if cfg.get("type") == "sequential_lessons":
                if cfg["value"].get("leader_plan_id") == plan_id:
                    return cfg["value"]
        return None

    def find_free_room(self, plan, slot):
        rooms = Room.objects.all().order_by("capacity")
        scheduled = self.memory_schedule.get(slot.id, [])
        occupied_ids = {item["room_id"] for item in scheduled}
        needed_cap = plan.target_audience_size
        
        # Збираємо всі підходящі аудиторії
        available_rooms = []
        for room in rooms:
            if plan.required_room_type and room.room_type != plan.required_room_type: 
                continue
            if room.capacity < needed_cap: 
                continue
            if room.id in occupied_ids: 
                continue
            
            # Перевіряємо обмеження для цієї аудиторії
            if not self.check_room_constraints(room, slot):
                continue
            
            available_rooms.append(room)
        
        if not available_rooms:
            return None
        
        # Вибираємо аудиторію з найменшою займаністю (для рівномірного розподілу)
        # Лічимо, скільки уроків вже в цій аудиторії в поточний день
        room_usage_count = {}
        for room in available_rooms:
            count = 0
            # Лічимо з пам'яті
            for slot_id, items in self.memory_schedule.items():
                slot_from_cache = self.time_slots_cache.get(slot_id)
                if slot_from_cache and slot_from_cache.date == slot.date:
                    count += sum(1 for item in items if item.get("room_id") == room.id)
            room_usage_count[room.id] = count
        
        # Вибираємо аудиторію з найменшою займаністю
        least_used_room = min(available_rooms, key=lambda r: room_usage_count[r.id])
        return least_used_room
    
    def check_room_constraints(self, room, slot):
        """Перевіряє обмеження для конкретної аудиторії"""
        for c in self.constraints:
            if not c.room_id or c.room_id != room.id:
                continue
            
            cfg = c.configuration
            ctype = cfg.get("type")
            
            if ctype == "max_daily_lessons":
                limit = cfg.get("value", 4)
                
                # Лічимо уроки з бази даних
                query = Lesson.objects.filter(time_slot__date=slot.date, room_id=room.id)
                existing_count = query.count()
                
                # Додаємо уроки з пам'яті
                for slot_id, items in self.memory_schedule.items():
                    slot_from_cache = self.time_slots_cache.get(slot_id)
                    if slot_from_cache and slot_from_cache.date == slot.date:
                        existing_count += sum(1 for item in items if item.get("room_id") == room.id)
                
                if existing_count >= limit:
                    return False
        
        return True

    def check_availability(self, plan, slot):
        items = self.memory_schedule.get(slot.id, [])
        for item in items:
            if item["teacher_id"] == plan.teacher_id: return False
            
            if plan.group:
                if item["group_id"] == plan.group_id: return False
                if item["stream_id"] and plan.group_id in item["stream_group_ids"]: return False
            elif plan.stream:
                if item["stream_id"] == plan.stream_id: return False
                if item["group_id"] in [g.id for g in plan.stream.groups.all()]: return False
        return True

    def check_dynamic_constraints(self, plan, slot):
        applicable = []
        for c in self.constraints:
            is_relevant = False
            # Обмеження для аудиторії НЕ перевіряються тут (вони обробляються в find_free_room)
            if c.group_id and c.group_id == plan.group_id: is_relevant = True
            elif c.teacher_id and c.teacher_id == plan.teacher_id: is_relevant = True
            elif c.stream_id and c.stream_id == plan.stream_id: is_relevant = True
            elif plan.stream and c.group_id in [g.id for g in plan.stream.groups.all()]: is_relevant = True
            if is_relevant: applicable.append(c)

        for c in applicable:
            cfg = c.configuration
            ctype = cfg.get("type")
            
            if ctype == "day_off":
                if slot.day_of_week in cfg.get("days", []): return False
            
            if ctype == "time_block":
                blocks = cfg.get("value", {})
                day_key = str(slot.day_of_week)
                if day_key in blocks:
                    if slot.period_number in blocks[day_key]:
                        return False

            if ctype == "max_daily_lessons":
                limit = cfg.get("value", 4)
                
                query = Q(time_slot__date=slot.date)
                
                # Обмеження для конкретної аудиторії
                if c.room_id:
                    query &= Q(room_id=c.room_id)
                # Обмеження для викладача
                elif c.teacher_id:
                    query &= Q(study_plan__teacher_id=c.teacher_id)
                # Обмеження для групи
                elif c.group_id:
                    query &= (Q(study_plan__group_id=c.group_id) | Q(study_plan__stream__groups__id=c.group_id))
                # Обмеження для потоку
                elif c.stream_id:
                    query &= Q(study_plan__stream_id=c.stream_id)
                
                # Лічимо уроки з бази даних
                existing_count = Lesson.objects.filter(query).count()
                
                # Додаємо уроки з пам'яті (які щойно були створені в цей день)
                for slot_id, items in self.memory_schedule.items():
                    # Отримуємо дату слота з пам'яті або з бази
                    try:
                        slot_date = self.time_slots_cache.get(slot_id).date if hasattr(self, 'time_slots_cache') else TimeSlot.objects.get(id=slot_id).date
                    except:
                        continue
                    
                    if slot_date == slot.date:
                        for item in items:
                            # Перевіряємо відповідність обмеженню
                            should_count = False
                            if c.room_id and item.get("room_id") == c.room_id:
                                should_count = True
                            elif c.teacher_id and item.get("teacher_id") == c.teacher_id:
                                should_count = True
                            elif c.group_id and (item.get("group_id") == c.group_id or c.group_id in item.get("stream_group_ids", [])):
                                should_count = True
                            elif c.stream_id and item.get("stream_id") == c.stream_id:
                                should_count = True
                            
                            if should_count:
                                existing_count += 1
                
                if existing_count >= limit:
                    return False

        return True

    def check_exam_day_limit(self, plan, slot):
        """
        Перевіряє, чи є вже екзамен у групи в цей день.
        """
        my_group_ids = set()
        if plan.group: 
            my_group_ids.add(plan.group.id)
        if plan.stream: 
            my_group_ids.update(g.id for g in plan.stream.groups.all())

        if not my_group_ids:
            return True

        lessons_on_date = Lesson.objects.filter(
            time_slot__date=slot.date
        ).select_related('study_plan', 'study_plan__group', 'study_plan__stream', 'study_plan__class_type')

        for lesson in lessons_on_date:
            type_name = lesson.study_plan.class_type.name.lower()
            if "екзамен" not in type_name and "exam" not in type_name:
                continue

            other_group_ids = set()
            if lesson.study_plan.group:
                other_group_ids.add(lesson.study_plan.group.id)
            if lesson.study_plan.stream:
                other_group_ids.update(g.id for g in lesson.study_plan.stream.groups.all())

            intersection = my_group_ids.intersection(other_group_ids)
            
            if intersection:
                print(f"⛔ БЛОКУЮ: Дата {slot.date}. Група(и) {intersection} вже має екзамен '{lesson.study_plan.subject.name}'")
                return False

        return True

    def check_sequential(self, plan, slot):
        seq_config = None
        for c in self.constraints:
            if c.configuration.get("type") == "sequential_lessons":
                if c.configuration["value"].get("follower_plan_id") == plan.id:
                    seq_config = c.configuration["value"]
                    break
        
        if not seq_config: 
            return True

        leader_id = seq_config["leader_plan_id"]
        gap = seq_config["time_gap"]

        leader_lesson = (Lesson.objects
                    .filter(study_plan_id=leader_id)
                    .select_related('time_slot')
                    .order_by('-time_slot__date', '-time_slot__period_number')
                    .first())

        if not leader_lesson or not leader_lesson.time_slot:
            return False

        l_slot = leader_lesson.time_slot
        
        if gap == 1:
            if slot.date == l_slot.date and slot.period_number == l_slot.period_number + 1: return True
            return False
        
        if gap == 0:
            if slot.id == l_slot.id: return True
            return False

        if slot.date > l_slot.date: return True
        if slot.date == l_slot.date and slot.period_number > l_slot.period_number + gap: return True

        return False
