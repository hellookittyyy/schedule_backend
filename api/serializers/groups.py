from rest_framework import serializers
from django.utils import timezone
from api.models import Group, Stream

class GroupSerializer(serializers.ModelSerializer):
    current_course = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ['id', 'name', 'amount', 'start_year', 'current_course']

    def get_current_course(self, obj):
        today = timezone.now().date()
        current_year = today.year
        
        if today.month >= 8:
            academic_year_start = current_year
        else:
            academic_year_start = current_year - 1
            
        course = (academic_year_start - obj.start_year) + 1
        
        if course < 1:
            return 0
        if course > 6:
            return "Випускник"
            
        return course

class StreamSerializer(serializers.ModelSerializer):
    groups = serializers.PrimaryKeyRelatedField(
        many=True, 
        queryset=Group.objects.all(),
        write_only=True 
    )
    
    groups_details = GroupSerializer(
        source='groups', 
        many=True, 
        read_only=True
    )

    total_students = serializers.SerializerMethodField()

    class Meta:
        model = Stream
        fields = ['id', 'name', 'groups', 'groups_details', 'total_students']

    def get_total_students(self, obj):
        return sum(group.amount for group in obj.groups.all())
