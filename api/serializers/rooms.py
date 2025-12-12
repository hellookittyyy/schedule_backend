from rest_framework import serializers
from api.models import Room, RoomType

class RoomTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomType
        fields = '__all__'

class RoomSerializer(serializers.ModelSerializer):
    room_type_details = RoomTypeSerializer(source='room_type', read_only=True)
    
    class Meta:
        model = Room
        fields = ['id', 'title', 'building', 'capacity', 'room_type', 'room_type_details', 'note']
        extra_kwargs = {
            'room_type': {'write_only': True}
        }