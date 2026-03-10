from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.db import transaction
from .models import CourseSection, CourseModule, FileResource, UrlResource
from testing.models import Quiz
from .permissions import can_manage_course

@login_required
@require_POST
def add_course_module(request):
    section_id = request.POST.get('section_id')
    module_type = request.POST.get('module_type')
    title = request.POST.get('title')
    
    section = CourseSection.objects.get(id=section_id)
    
    if not can_manage_course(request.user, section.course):
        return JsonResponse({'success': False, 'error': 'Нет прав'})
    
    last_seq = section.modules.count()
    
    with transaction.atomic():
        module = CourseModule.objects.create(
            section=section,
            module_type=module_type,
            title=title,
            sequence=last_seq + 1
        )
        
        if module_type == 'FILE':
            file_obj = request.FILES.get('file')
            if file_obj:
                FileResource.objects.create(module=module, file=file_obj, display_type='DOWNLOAD')
        elif module_type == 'URL':
            UrlResource.objects.create(module=module, external_url=request.POST.get('external_url'))
        elif module_type == 'QUIZ':
            Quiz.objects.create(module=module, description="Новый тест")
            
    return JsonResponse({'success': True, 'module_id': module.id})