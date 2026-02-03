from rest_framework import serializers
from api.models import Teacher, Subject
from .subjects import SubjectSerializer

class TeacherSerializer(serializers.ModelSerializer):
    subjects_details = SubjectSerializer(source='subjects', many=True, read_only=True)
    
    class Meta:
        model = Teacher
        fields = ['id', 'name', 'subjects', 'subjects_details']
        extra_kwargs = {'subjects': {'write_only': True, 'required': False}}

    def create(self, validated_data):
        subjects = validated_data.pop('subjects', [])
        teacher = Teacher.objects.create(**validated_data)
        
        if subjects:
            teacher.subjects.set(subjects)
        
        return teacher

    def update(self, instance, validated_data):
        subjects = validated_data.pop('subjects', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if subjects is not None:
            instance.subjects.set(subjects)
        
        return instance