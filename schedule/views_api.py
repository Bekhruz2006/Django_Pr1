import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.db import transaction
from .models import Subject, Subgroup
from accounts.models import Group, Student

@login_required
@require_POST
def generate_subgroups(request):
    data = json.loads(request.body)
    subject_id = data.get('subject_id')
    group_id = data.get('group_id')
    count = int(data.get('count', 2))

    subject = Subject.objects.get(id=subject_id)
    group = Group.objects.get(id=group_id)

    with transaction.atomic():
        Subgroup.objects.filter(subject=subject, group=group, students__isnull=True).delete()
        
        subgroups = []
        for i in range(1, count + 1):
            sg, created = Subgroup.objects.get_or_create(
                subject=subject, 
                group=group, 
                name=f"Подгруппа {i}"
            )
            subgroups.append({"id": sg.id, "name": sg.name})

    return JsonResponse({"success": True, "subgroups": subgroups})

@login_required
@require_POST
def save_subgroups_drag_drop(request):
    data = json.loads(request.body)
    
    with transaction.atomic():
        for sg_data in data.get('subgroups', []):
            subgroup = Subgroup.objects.get(id=sg_data['id'])
            
            if sg_data.get('teacher_id'):
                subgroup.teacher_id = sg_data['teacher_id']
            
            if 'student_ids' in sg_data:
                subgroup.students.set(sg_data['student_ids'])
            
            subgroup.save()

    return JsonResponse({"success": True})