from django.db import transaction
from rest_framework import serializers
from api.exceptions import ScheduleExists
from api.models import Semester, TimeSlot, SemesterConstraint, Lesson, StudyPlan, Room

class TimeSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeSlot
        fields = [
            'id', 'semester', 'date', 'start_time', 'end_time', 
            'period_number', 'week_type', 'day_of_week', 'day_name', 'is_available'
        ]

class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ['id', 'title', 'building', 'capacity']

class StudyPlanDepthSerializer(serializers.ModelSerializer):
    """Серіалізатор для детального відображення даних навчального плану"""
    subject = serializers.CharField(source='subject.name')
    teacher = serializers.CharField(source='teacher.name')
    group = serializers.CharField(source='group.name', allow_null=True)
    stream = serializers.CharField(source='stream.name', allow_null=True)
    class_type = serializers.CharField(source='class_type.name')
    
    class Meta:
        model = StudyPlan
        fields = [
            'id', 'subject', 'teacher', 'group', 'stream', 'class_type', 'duration',
            'group_id', 'stream_id', 'teacher_id', 'subject_id', 'class_type_id',
        ]


def normalize_semester_config(config):
    """Return ``(time_schedule, weekends)`` from a semester configuration dict."""
    config = config or {}
    if 'generation_config' in config:
        config = config['generation_config'] or {}
    return config.get('time_schedule') or [], config.get('weekends') or []


class SemesterSerializer(serializers.ModelSerializer):
    generation_config = serializers.JSONField(write_only=True, required=False)
    confirm_schedule_deletion = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Semester
        fields = [
            'id', 'name', 'start_date', 'end_date', 'configuration',
            'generation_config', 'confirm_schedule_deletion', 'is_current',
        ]
        read_only_fields = ['configuration']

    def create(self, validated_data):
        validated_data.pop('confirm_schedule_deletion', False)
        config = validated_data.pop('generation_config', {})
        validated_data['configuration'] = config

        semester = super().create(validated_data)

        if config:
            semester.synchronize_slots()

        return semester

    def _slot_inputs(self, instance, validated_data, config, has_config):
        """Slot-affecting inputs: dates plus the normalised schedule/weekends."""
        if has_config:
            new_config = config
        else:
            new_config = instance.configuration

        time_schedule, weekends = normalize_semester_config(new_config)
        return (
            validated_data.get('start_date', instance.start_date),
            validated_data.get('end_date', instance.end_date),
            time_schedule,
            weekends,
        )

    def update(self, instance, validated_data):
        confirm = validated_data.pop('confirm_schedule_deletion', False)
        has_config = 'generation_config' in validated_data
        config = validated_data.pop('generation_config', None)

        time_schedule, weekends = normalize_semester_config(instance.configuration)
        old_inputs = (instance.start_date, instance.end_date, time_schedule, weekends)
        new_inputs = self._slot_inputs(instance, validated_data, config, has_config)
        resync = old_inputs != new_inputs

        if has_config:
            validated_data['configuration'] = config or {}

        if not resync:
            return super().update(instance, validated_data)

        lessons = Lesson.objects.filter(study_plan__semester=instance)
        if lessons.exists():
            if not confirm:
                # Нічого не зберігаємо: дати, слоти й заняття лишаються як були.
                raise ScheduleExists()

            with transaction.atomic():
                deleted_count = lessons.delete()[0]
                instance = super().update(instance, validated_data)
                instance.synchronize_slots(force_delete=True)
                instance.deleted_lessons = deleted_count
            return instance

        instance = super().update(instance, validated_data)
        instance.synchronize_slots()
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        deleted_lessons = getattr(instance, 'deleted_lessons', None)
        if deleted_lessons is not None:
            data['deleted_lessons'] = deleted_lessons
        return data


class SemesterConstraintSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.name', read_only=True)
    group_name = serializers.CharField(source='group.name', read_only=True)
    stream_name = serializers.CharField(source='stream.name', read_only=True)
    room_name = serializers.CharField(source='room.title', read_only=True)

    class Meta:
        model = SemesterConstraint
        fields = [
            'id', 'semester', 
            'teacher', 'teacher_name',
            'group', 'group_name',
            'stream', 'stream_name',
            'room', 'room_name',
            'configuration', 'is_active'
        ]

    def validate(self, data):
          teacher = data.get('teacher')
          group = data.get('group')
          stream = data.get('stream')
          room = data.get('room')
          
          entities = [teacher, group, stream, room]
          set_count = sum(1 for e in entities if e is not None)
          
          configuration = data.get('configuration', {})
          if not configuration and self.instance:
              configuration = self.instance.configuration
              
          config_type = configuration.get('type') if configuration else None
          
          SPECIAL_TYPES = ['sequential_lessons']

          if set_count == 0:
              if config_type in SPECIAL_TYPES:
                  return data
              else:
                  raise serializers.ValidationError("Необхідно вказати хоча б одну сутність (викладач, група, потік або аудиторія).")
          
          if set_count > 1:
              raise serializers.ValidationError("Можна вказати лише одну сутність.")
          
          return data


class LessonSerializer(serializers.ModelSerializer):
    time_slot_details = TimeSlotSerializer(source='time_slot', read_only=True)
    study_plan_details = StudyPlanDepthSerializer(source='study_plan', read_only=True)
    room_details = RoomSerializer(source='room', read_only=True)

    class Meta:
        model = Lesson
        fields = [
            'id', 
            'is_locked',
            'time_slot',       
            'study_plan',
            'room',
            'time_slot_details', 
            'study_plan_details',
            'room_details',
        ]
