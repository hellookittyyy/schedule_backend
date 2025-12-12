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
            
            if not plans:
                return {"success": False, "error": "No study plans found"}
            
            sorted_plans = self.sort_plans(plans)

            time_slots = list(TimeSlot.objects.filter(
                semester=self.semester, is_available=True
            ).order_by("date", "period_number"))
            
            if not time_slots:
                return {"success": False, "error": "No time slots found"}

            created_count = 0
            unassigned_count = 0

            for plan_idx, plan in enumerate(sorted_plans, 1):
                target_name = plan.group.name if plan.group else (plan.stream.name if plan.stream else "Unknown")
                self.log(f"[{plan_idx}/{len(sorted_plans)}] Processing: {plan.subject.name} ({plan.class_type.name}) -> {target_name}")

                for i in range(plan.amount):
                    try:
                        slot = None
                        room = None
                        
                        with transaction.atomic():
                            slot, room = self.find_and_assign_slot(plan, time_slots)
                            
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
                                self.log(f"   Warning: No slot found for lesson {i+1}. Added to Unassigned.")
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

    def register_memory(self, plan, slot, room):
        self.memory_schedule[slot.id].append({
            "plan_id": plan.id,
            "teacher_id": plan.teacher_id,
            "group_id": plan.group_id,
            "stream_id": plan.stream_id,
            "room_id": room.id if room else None,
            "stream_group_ids": [g.id for g in plan.stream.groups.all()] if plan.stream else []
        })

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

    def find_and_assign_slot(self, plan, time_slots):
        print(f"DEBUG: Plan ID={plan.id}, Type='{plan.class_type.name}'")
        is_current_plan_exam = "екзамен" in plan.class_type.name.lower() or "exam" in plan.class_type.name.lower()
        
        follower_config = self.get_follower_config(plan.id)

        for idx, slot in enumerate(time_slots):
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

        for room in rooms:
            if plan.required_room_type and room.room_type != plan.required_room_type: continue
            if room.capacity < needed_cap: continue
            if room.id in occupied_ids: continue
            return room
        return None

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
                
                count = 0
                target_ids = []
                if plan.group: target_ids.append(plan.group.id)
                if plan.stream: target_ids.extend([g.id for g in plan.stream.groups.all()])
                
                for s_id, items in self.memory_schedule.items():
                    pass

                query = Q(time_slot__date=slot.date)
                if plan.group:
                    query &= (Q(study_plan__group=plan.group) | Q(study_plan__stream__groups=plan.group))
                elif plan.teacher:
                    query &= Q(study_plan__teacher=plan.teacher)
                
                existing_count = Lesson.objects.filter(query).count()
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