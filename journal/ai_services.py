import requests
import json
import logging
from journal.models import StudentStatistics, StudentPerformancePrediction

logger = logging.getLogger(__name__)

class AIStudentAnalyzer:
    OLLAMA_URL = "http://localhost:11434/api/generate"

    @staticmethod
    def analyze_at_risk_students():
        at_risk_stats = StudentStatistics.objects.filter(overall_gpa__lt=3.5) | StudentStatistics.objects.filter(attendance_percentage__lt=70.0)
        
        for stat in at_risk_stats[:10]: 
            prompt = f"""
            Проанализируй данные студента и дай короткий прогноз риска отчисления.
            Студент: {stat.student.user.get_full_name()}
            Курс: {stat.student.course}
            GPA: {stat.overall_gpa}
            Посещаемость: {stat.attendance_percentage}%
            Прогулов: {stat.total_absent}
            
            Верни ответ строго в JSON формате:
            {{
                "risk_level": "HIGH" или "MEDIUM",
                "predicted_gpa": число (прогноз),
                "notes": "Краткая причина и рекомендация на русском языке"
            }}
            """
            
            try:
                resp = requests.post(AIStudentAnalyzer.OLLAMA_URL, json={
                    "model": "gemma3:4b", # Или llama3
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2}
                }, timeout=30)
                
                if resp.status_code == 200:
                    import re
                    raw = resp.json().get("response", "")
                    match = re.search(r'\{[\s\S]*\}', raw)
                    if match:
                        data = json.loads(match.group(0))
                        StudentPerformancePrediction.objects.update_or_create(
                            student=stat.student,
                            defaults={
                                'risk_level': data.get('risk_level', 'MEDIUM'),
                                'predicted_gpa': data.get('predicted_gpa', stat.overall_gpa),
                                'notes': data.get('notes', 'Анализ завершен.')
                            }
                        )
            except Exception as e:
                logger.error(f"AI Analysis error: {e}")