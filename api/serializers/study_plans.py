from rest_framework import serializers
from api.models import StudyPlan, ClassType

class ClassTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassType
        fields = '__all__'

class StudyPlanSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    teacher_name = serializers.CharField(source='teacher.name', read_only=True)
    group_name = serializers.CharField(source='group.name', read_only=True)
    stream_name = serializers.CharField(source='stream.name', read_only=True)
    class_type_name = serializers.CharField(source='class_type.name', read_only=True)
    room_type_name = serializers.CharField(source='required_room_type.name', read_only=True)
    
    course_number = serializers.IntegerField(
        write_only=True, 
        required=False,
        allow_null=True,
        help_text="Номер курсу (1-6) для масового створення StudyPlan для всіх груп цього курсу"
    )

    class Meta:
        model = StudyPlan
        fields = [
            'id', 'semester', 
            'group', 'group_name',
            'stream', 'stream_name',
            'subject', 'subject_name', 
            'teacher', 'teacher_name', 
            'class_type', 'class_type_name', 
            'required_room_type', 'room_type_name',
            'duration',
            'amount',
            'constraints',
            'course_number'  
        ]

    def validate(self, data):
        # Видалити course_number з data, щоб не передавати в модель
        course_number = data.pop('course_number', None)
        
        # Якщо є course_number - то це масове створення, пропустити стандартну валідацію
        if course_number is not None:
            return data
        
        # 1. Teacher Qualification
        teacher = data.get('teacher')
        subject = data.get('subject')
        
        # Handle partial updates
        if self.instance:
            teacher = teacher or self.instance.teacher
            subject = subject or self.instance.subject

        if teacher and subject:
            if not teacher.subjects.filter(id=subject.id).exists():
                raise serializers.ValidationError({
                    "teacher": f"Викладач {teacher.name} не має кваліфікації для предмету '{subject.name}'."
                })

        # 2. Group XOR Stream
        group = data.get('group')
        stream = data.get('stream')
        
        if self.instance:
            current_group = data['group'] if 'group' in data else self.instance.group
            current_stream = data['stream'] if 'stream' in data else self.instance.stream
        else:
            current_group = group
            current_stream = stream

        if current_group and current_stream:
            raise serializers.ValidationError("Не можна вказувати і Групу, і Потік одночасно.")
        if not current_group and not current_stream:
            raise serializers.ValidationError("Необхідно вказати або Групу, або Потік.")

        return data