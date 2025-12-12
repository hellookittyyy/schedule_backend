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
            'constraints'
        ]

    def validate(self, data):
        """
        Validate business logic:
        1. Teacher qualification.
        2. XOR Logic for Group vs Stream.
        """
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
        
        # Note: We need to be careful with partial updates. 
        # If updating, we should check the final state.
        if self.instance:
            # If 'group' is not in data, use instance.group (unless explicit None passed?)
            # DRF validation typically passes provided data.
            # Let's rely on model.clean() but implementing it here gives better API errors.
            
            # Explicitly checking what is provided in 'data' vs what is in 'instance'
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