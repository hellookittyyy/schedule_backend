
import os
import django
import sys
from django.utils.text import slugify

# Setup Django environment
sys.path.append('/Users/oleksii.velychko/Documents/WORK/ScheduleBackend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from api.models import RoomType

def populate_slugs():
    print("Populating RoomType slugs...")
    types = RoomType.objects.all()
    for rt in types:
        base_slug = slugify(rt.name)
        if not base_slug:
            # Fallback for non-ASCII
            base_slug = f"type-{rt.id}"
        
        slug = base_slug
        counter = 1
        while RoomType.objects.filter(slug=slug).exclude(id=rt.id).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        rt.slug = slug
        rt.save()
        print(f"Updated {rt.name} -> {rt.slug}")

if __name__ == "__main__":
    populate_slugs()
