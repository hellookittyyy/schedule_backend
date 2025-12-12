from rest_framework import serializers
from api.models import Teacher, Subject
from .subjects import SubjectSerializer

class TeacherSerializer(serializers.ModelSerializer):
    subjects_details = SubjectSerializer(source='subjects', many=True, read_only=True)
    
    class Meta:
        model = Teacher
        fields = ['id', 'name', 'subjects', 'subjects_details']
        extra_kwargs = {'subjects': {'write_only': True}}