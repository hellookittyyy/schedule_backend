from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from api.services.generator import ScheduleGenerator

class GenerateScheduleView(APIView):
    def post(self, request):
        semester_id = request.data.get('semester_id')
        
        if not semester_id:
            return Response(
                {"error": "semester_id is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            generator = ScheduleGenerator(semester_id)
            result = generator.generate()
            
            return Response(result, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Generation Error: {str(e)}")
            return Response(
                {"error": str(e), "success": False}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )