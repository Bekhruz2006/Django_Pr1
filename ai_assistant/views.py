from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from .services import query_ollama, extract_text_from_file
from .tools import execute_action
import json

@login_required
def chat_view(request):
    return render(request, 'ai_assistant/chat.html')

@login_required
@require_POST
def chat_api(request):
    try:
        user_message = request.POST.get('message', '')
        uploaded_file = request.FILES.get('file')
        
        file_context = ""
        if uploaded_file:
            file_context = extract_text_from_file(uploaded_file)
            if not user_message:
                user_message = "Проанализируй файл."
        intent_json = query_ollama(request.user, user_message, file_context)
        
        bot_response = execute_action(request.user, intent_json)
            
        return JsonResponse({
            'response': bot_response, 
            'debug': intent_json 
        })
        
    except Exception as e:
        return JsonResponse({'response': f"Ошибка: {str(e)}"}, status=500)