import json
import logging
import re
import os
import requests
from concurrent.futures import ThreadPoolExecutor
from django.db import close_old_connections
from django.utils import timezone

logger = logging.getLogger(__name__)

_OLLAMA_URL = "http://localhost:11434/api/generate"
_LLM_TIMEOUT = 180

_TASK_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="rup_parser")

_STOP_WORDS_RE = re.compile(
    r"""
    ректори | вазорати | тасдиқ  | тасдик | имзо   | мӯҳр   | сана
    | донишгоҳи | муассиса | факултети | институт
    | курсҳо | нимсола | семестр
    | эзоҳ | шарҳ | изоҳ | примечани
    | итого | всего | барча | ҷамъ | жами
    """,
    re.IGNORECASE | re.VERBOSE | re.UNICODE,
)

_JUNK_LINE_RE = re.compile(
    r"""
    ^                                  
    (?:
    (?:I{1,3}|IV|VI{0,3}|IX|X{1,3})  
    \s*
    |
    \d+\s*$                           
    )
    """,
    re.VERBOSE | re.UNICODE,
)


def _clean_text_lines(raw_text: str) -> str:
    cleaned: list[str] = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if len(line) < 5 or _STOP_WORDS_RE.search(line) or _JUNK_LINE_RE.match(line):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def parse_rup_with_llm_task(task_id: str, file_path: str, filename: str) -> None:
    close_old_connections()
    try:
        _run(task_id, file_path, filename)
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        close_old_connections()


def _run(task_id: str, file_path: str, filename: str) -> None:
    from schedule.models import RupParseTask
    try:
        result = _llm_parse(file_path, filename)
        if not result:
            raise ValueError("LLM returned empty result")

        RupParseTask.objects.filter(pk=task_id).update(
            status="SUCCESS", result=result, finished_at=timezone.now()
        )
    except Exception as llm_exc:
        logger.warning("parse_rup_with_llm_task LLM failed task_id=%s — fallback to algorithmic", task_id)
        try:
            result = _algorithmic_parse(file_path, filename)
            RupParseTask.objects.filter(pk=task_id).update(
                status="SUCCESS", result=result, finished_at=timezone.now()
            )
        except Exception as fallback_exc:
            logger.error("parse_rup_with_llm_task FALLBACK FAILED task_id=%s error=%s", task_id, fallback_exc)
            RupParseTask.objects.filter(pk=task_id).update(
                status="FAILURE", error=str(fallback_exc), finished_at=timezone.now()
            )


def _llm_parse(file_path: str, filename: str) -> list:
    raw_text = _extract_text(file_path, filename)
    if not raw_text.strip():
        raise ValueError("Could not extract any text from the file")

    cleaned_text = _clean_text_lines(raw_text)
    if not cleaned_text.strip():
        raise ValueError("Text is empty after cleaning")

    prompt = (
        "Ты — ИИ-ассистент учебной части университета.\n"
        "Твоя задача: извлечь из учебного плана (РУП) список дисциплин.\n\n"
        "## Строгая JSON-схема каждого элемента результата:\n"
        "{\n"
        '  "name":    string,              // Полное название дисциплины\n'
        '  "credits": integer,             // Кредиты (целое число >= 0)\n'
        '  "lec":     integer,             // Аудиторные часы — Лекции\n'
        '  "prac":    integer,             // Аудиторные часы — Практика\n'
        '  "srsp":    integer,             // Аудиторные часы — СРСП / КМРО\n'
        '  "srs":     integer,             // Самостоятельная работа (СРС / КМД)\n'
        '  "type":    "REQUIRED" | "ELECTIVE"  // Тип дисциплины\n'
        "}\n\n"
        "## Few-Shot примеры:\n\n"
        "### Пример 1 — МУСОР (административная строка, не дисциплина):\n"
        'Вход: "Тасдиқ мекунам Асрорзода У.С. \\n 1.1 \\n 1"\n'
        "Ожидаемый выход: []\n\n"
        "### Пример 2 — МУСОР (шапка таблицы):\n"
        'Вход: "КУРСҲО \\n Семестр \\n I II III \\n Итого"\n'
        "Ожидаемый выход: []\n\n"
        "### Пример 3 — ВАЛИДНАЯ обязательная дисциплина:\n"
        'Вход: "Омӯзиши мошинӣ 5 32 16 0 16"\n'
        "Ожидаемый выход:\n"
        '[{"name": "Омӯзиши мошинӣ", "credits": 5, "lec": 32, "prac": 16, "srsp": 0, "srs": 16, "type": "REQUIRED"}]\n\n'
        "### Пример 4 — ВАЛИДНАЯ элективная дисциплина:\n"
        'Вход: "Веб-дизайн (интихобӣ) 3 16 16 16 0"\n'
        "Ожидаемый выход:\n"
        '[{"name": "Веб-дизайн", "credits": 3, "lec": 16, "prac": 16, "srsp": 16, "srs": 0, "type": "ELECTIVE"}]\n\n'
        "## Правила:\n"
        "1. Если строка — это заголовок, подпись, нумерация или итоговая строка — ПРОПУСТИ её.\n"
        "2. Если строка содержит римские цифры (I, II, III) как самостоятельный токен — ПРОПУСТИ.\n"
        "3. Если часы не указаны явно — выставь 0.\n"
        "4. Верни ТОЛЬКО JSON массив (без markdown-блоков, без пояснений).\n\n"
        f"## Очищенный текст учебного плана (первые 4000 символов):\n{cleaned_text[:4000]}\n\n"
        "## Ответ (JSON массив):"
    )

    payload = {
        "model": "gemma3:4b",
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 2048},
    }

    resp = requests.post(_OLLAMA_URL, json=payload, timeout=_LLM_TIMEOUT)
    resp.raise_for_status()
    raw_response = resp.json().get("response", "")
    return _extract_json_list(raw_response)


def _algorithmic_parse(file_path: str, filename: str) -> list:
    from schedule.services import RupImporter
    with open(file_path, 'rb') as f:
        return RupImporter.parse_for_preview(f)


def _extract_text(file_path: str, filename: str) -> str:
    name = filename.lower()

    if name.endswith(".pdf"):
        import pdfplumber
        pages_text = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages[:10]:
                page_text = page.extract_text() or ""
                pages_text.append(page_text)
        return "\n".join(pages_text)

    if name.endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheet = wb.active
        rows = []
        for row in sheet.iter_rows(min_row=1, max_row=100, values_only=True):
            cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
            if cells:
                rows.append(" | ".join(cells))
        return "\n".join(rows)

    raise ValueError(f"Unsupported file type. Use .pdf or .xlsx: {filename}")


def _extract_json_list(raw: str) -> list:
    if not raw or not raw.strip():
        raise ValueError("LLM response is empty")

    match = re.search(r'\[\s*\{.*?\}\s*\]', raw, re.DOTALL)
    if not match:
        match = re.search(r'\[.*?\]', raw, re.DOTALL)

    if not match:
        raise ValueError("No JSON array found in LLM response")

    json_str = match.group(0)

    try:
        result = json.loads(json_str)
    except json.JSONDecodeError:
        json_str_fixed = re.sub(r",\s*([}\]])", r"\1", json_str)
        try:
            result = json.loads(json_str_fixed)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Cannot parse JSON from LLM response: {exc}") from exc

    if not isinstance(result, list):
        raise ValueError(f"Expected a JSON array from LLM, got {type(result).__name__}")

    normalised: list[dict] = []
    for item in result:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if len(name) < 3:
            continue
        normalised.append({
            "name": name,
            "credits": int(item.get("credits") or 0),
            "lec":     int(item.get("lec")     or 0),
            "prac":    int(item.get("prac")    or 0),
            "srsp":    int(item.get("srsp")    or 0),
            "srs":     int(item.get("srs")     or 0),
            "type":    str(item.get("type", "REQUIRED")).upper(),
        })

    return normalised


def start_parse_task(task_id: str, file_path: str, filename: str) -> None:
    _TASK_EXECUTOR.submit(parse_rup_with_llm_task, task_id, file_path, filename)
    logger.info("start_parse_task: added to ThreadPoolQueue task_id=%s filename=%s", task_id, filename)