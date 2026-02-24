from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.db import transaction
from .models import CourseSection, CourseModule, Resource, UrlResource
from testing.models import Quiz

@login_required
@require_POST
def add_course_module(request):
    section_id = request.POST.get('section_id')
    module_type = request.POST.get('module_type')
    title = request.POST.get('title')
    
    section = CourseSection.objects.get(id=section_id)
    last_seq = section.modules.count()
    
    with transaction.atomic():
        module = CourseModule.objects.create(
            section=section,
            module_type=module_type,
            title=title,
            sequence=last_seq + 1
        )
        
        if module_type == 'RESOURCE':
            Resource.objects.create(module=module, content=request.POST.get('content', ''), file=request.FILES.get('file'))
        elif module_type == 'URL':
            UrlResource.objects.create(module=module, external_url=request.POST.get('external_url'))
        elif module_type == 'QUIZ':
            Quiz.objects.create(module=module, description="Новый тест")
            
    return JsonResponse({'success': True, 'module_id': module.id})