import datetime
from datetime import timedelta
from api.models import TimeSlot

def generate_semester_slots(semester_instance, config):
    """
    semester_instance: об'єкт моделі Semester
    config: словник (JSON) з параметрами, які прийшли з фронтенду
    """
    
    current_date = semester_instance.start_date
    end_date = semester_instance.end_date
    
    weekends = config.get("weekends", [])
    time_schedule = config.get("time_schedule", [])
    
    dates_excluded = set(config.get("dates_excluded", []))
    dates_included = set(config.get("dates_included", []))
    
    day_time_excluded = config.get("day_time_excluded", {})
    date_time_excluded = config.get("date_time_excluded", {})

    new_slots = []

    while current_date <= end_date:
        day_name_full = current_date.strftime("%A")
        current_date_str = current_date.strftime("%Y-%m-%d") 
        
        is_weekend = day_name_full in weekends
        if current_date_str in dates_excluded or (is_weekend and current_date_str not in dates_included):
            current_date += timedelta(days=1)
            continue
        
        is_day_in_time_excluded = day_name_full in day_time_excluded
        is_date_in_time_excluded = current_date_str in date_time_excluded

        for time_pair in time_schedule:
            start_t_str = time_pair[0]
            end_t_str = time_pair[1]

            if is_day_in_time_excluded and start_t_str in day_time_excluded[day_name_full]:
                continue

            if is_date_in_time_excluded and start_t_str in date_time_excluded[current_date_str]:
                continue
            
            new_slots.append(TimeSlot(
                semester=semester_instance,
                date=current_date,
                start_time=datetime.datetime.strptime(start_t_str, "%H:%M").time(),
                end_time=datetime.datetime.strptime(end_t_str, "%H:%M").time(),
                day_name=day_name_full
            ))

        current_date += timedelta(days=1)

    TimeSlot.objects.filter(semester=semester_instance).delete()
    
    TimeSlot.objects.bulk_create(new_slots)
    
    return len(new_slots)