import requests
import json
import pdfplumber
import openpyxl
import datetime
import re

MODEL_NAME = "mistral:7b" 
OLLAMA_URL = "http://localhost:11434/api/generate"

def extract_text_from_file(uploaded_file):
    text_content = ""
    try:
        filename = uploaded_file.name.lower()
        if filename.endswith('.pdf'):
            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages[:5]:
                    extracted = page.extract_text()
                    if extracted: text_content += extracted + "\n"
        elif filename.endswith(('.xlsx', '.xls')):
            wb = openpyxl.load_workbook(uploaded_file, data_only=True)
            sheet = wb.active
            for row in sheet.iter_rows(values_only=True, max_row=100):
                row_text = " | ".join([str(c).strip() for c in row if c is not None])
                text_content += row_text + "\n"
        elif filename.endswith('.txt'):
            text_content = uploaded_file.read().decode('utf-8')
    except Exception as e:
        return f"Error reading file: {str(e)}"
    
    return text_content[:10000]

def get_system_prompt(user):
    today = datetime.date.today().strftime("%Y-%m-%d")
    
    role_context = "Сотрудник"
    if user.role == 'DEAN': role_context = "Декан факультета"
    elif user.role == 'TEACHER': role_context = "Преподаватель"
    elif user.role == 'STUDENT': role_context = "Студент"

    prompt = f"""
    Ты — интеллектуальный администратор базы данных университета (Django).
    Твоя цель: преобразовать запрос пользователя (на русском языке) в точную JSON-команду.

    КОНТЕКСТ:
    - Дата: {today}
    - Роль пользователя: {role_context} ({user.get_full_name()})

    === СТРАТЕГИЯ ИЗВЛЕЧЕНИЯ ДАННЫХ (ВАЖНО) ===
    1. **Очистка сущностей**: Если пользователь пишет "для кафедры Политологии", в поле `search_query` пиши ТОЛЬКО "Политология". Убирай слова "кафедра", "группа", "предмет".
    2. **Типы поиска (search_type)**:
       - "department": Если упомянута кафедра, факультет или направление (пример: "для экономистов", "кафедра физики").
       - "course": Если упомянут только курс (пример: "для всех 2 курса", "первокурсникам").
       - "group": Если упомянуто конкретное название группы (пример: "40101", "группа А").
    3. **Кредиты**: Если не указаны, ставь 4.
    4. **Потоки**: Если запрос подразумевает несколько групп (например, "для всех групп", "для кафедры", "поток"), ставь `"is_stream": true`.

    === ДОСТУПНЫЕ КОМАНДЫ (JSON) ===

    1. **Добавить предмет** (add_subject):
    {{
        "action": "add_subject",
        "params": {{
            "name": "Название предмета (чистое)",
            "credits": 3 (int),
            "search_type": "department" | "course" | "group",
            "search_query": "Ключевое слово для поиска (без лишних слов)",
            "is_stream": true/false
        }}
    }}

    2. **Добавить в расписание** (add_schedule):
    {{
        "action": "add_schedule",
        "params": {{
            "group_query": "Название группы",
            "subject_query": "Название предмета",
            "day": 0 (0=Пн, 1=Вт ... 5=Сб),
            "time": "08:00" (формат ЧЧ:ММ),
            "room": "101" (если есть),
            "is_military": false (true если это "военная кафедра")
        }}
    }}
    4. **Удалить предмет** (delete_subject):
    {{
        "action": "delete_subject",
        "params": {{
            "name": "Название предмета",
            "search_query": "Кафедра или группа для уточнения"
        }}
    }}
    5. **Вопрос/Уточнение** (question):
    Если в запросе нет названия предмета или непонятно, кому его добавить.
    {{ "action": "question", "text": "Уточните, какой предмет и для кого добавить?" }}

    6. **Чат/Анализ** (chat):
    Для приветствий или вопросов по содержимому файла.
    {{ "action": "chat", "text": "Ваш ответ..." }}

    === ПРИМЕРЫ (Few-Shot Learning) ===
    
    User: "Добавь Математику 3 кредита для кафедры политология"
    Assistant: {{
        "action": "add_subject", 
        "params": {{
            "name": "Математика", 
            "credits": 3, 
            "search_type": "department", 
            "search_query": "политология", 
            "is_stream": false
        }}
    }}

    User: "Поставь Физику всем 2 курсникам"
    Assistant: {{
        "action": "add_subject", 
        "params": {{
            "name": "Физика", 
            "credits": 4, 
            "search_type": "course", 
            "search_query": "2", 
            "is_stream": true
        }}
    }}

    User: "В среду в 8 утра у группы 401 будет История в 205 кабинете"
    Assistant: {{
        "action": "add_schedule", 
        "params": {{
            "group_query": "401", 
            "subject_query": "История", 
            "day": 2, 
            "time": "08:00", 
            "room": "205"
        }}
    }}
    
    User: "Удали Математику у политологов"
    JSON: {{"action": "delete_subject", "params": {{"name": "Математика", "search_query": "политология"}}}}

    ОТВЕЧАЙ ТОЛЬКО JSON. БЕЗ КОММЕНТАРИЕВ.
    """
    return prompt

def query_ollama(user, user_text, file_context=""):
    system_prompt = get_system_prompt(user)
    
    full_prompt = f"{system_prompt}\n"
    if file_context:
        full_prompt += f"\n--- НАЧАЛО ФАЙЛА ---\n{file_context}\n--- КОНЕЦ ФАЙЛА ---\n"
        full_prompt += "Используй информацию из файла выше, если пользователь просит 'проанализировать' или 'добавить из файла'.\n"
    
    full_prompt += f"\nUSER QUERY: {user_text}\nJSON OUTPUT:"

    payload = {
        "model": MODEL_NAME,
        "prompt": full_prompt,
        "stream": False,
        "format": "json", # Принудительный JSON режим
        "temperature": 0.1, # Минимальная креативность для точности
        "options": {
            "num_ctx": 8192, # Увеличенное окно контекста (для файлов)
            "num_predict": 512, # Макс длина ответа
            "top_k": 20,
            "top_p": 0.9
        }
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=3000)
        response.raise_for_status()
        result = response.json()
        
        clean_json = result['response'].strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json[7:]
        if clean_json.endswith("```"):
            clean_json = clean_json[:-3]
            
        return json.loads(clean_json)
    except requests.exceptions.Timeout:
        return {"action": "chat", "text": "⏳ Время ожидания истекло (300 сек). Модель работает медленно. Попробуйте упростить запрос или разбить его на части."}
    except requests.exceptions.ConnectionError:
        return {"action": "chat", "text": "🔌 Не могу подключиться к Ollama. Убедитесь, что 'ollama serve' запущен."}
    except json.JSONDecodeError:
        return {"action": "chat", "text": f"⚠️ Модель вернула некорректный ответ. Попробуйте снова.\nОтвет: {result.get('response', '')[:100]}..."}
    except Exception as e:
        return {"action": "chat", "text": f"❌ Системная ошибка: {str(e)}"}