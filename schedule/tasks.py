import json
import logging
import re
import threading
import pdfplumber
import requests
from django.db import close_old_connections
from django.utils import timezone

logger = logging.getLogger(__name__)

_OLLAMA_URL = "http://localhost:11434/api/generate"
_LLM_TIMEOUT = 180


def parse_rup_with_llm_task(task_id: str, file_bytes: bytes, filename: str) -> None:
    close_old_connections()
    try:
        _run(task_id, file_bytes, filename)
    finally:
        close_old_connections()


def _run(task_id: str, file_bytes: bytes, filename: str) -> None:
    from schedule.models import RupParseTask

    try:
        result = _llm_parse(file_bytes, filename)
        if not result:
            raise ValueError("LLM returned empty result")
        RupParseTask.objects.filter(pk=task_id).update(
            status="SUCCESS",
            result=result,
            finished_at=timezone.now(),
        )
        logger.info("parse_rup_with_llm_task SUCCESS task_id=%s items=%s", task_id, len(result))

    except Exception as llm_exc:
        logger.warning(
            "parse_rup_with_llm_task LLM failed task_id=%s error=%s — fallback to algorithmic",
            task_id,
            llm_exc,
        )
        try:
            result = _algorithmic_parse(file_bytes, filename)
            RupParseTask.objects.filter(pk=task_id).update(
                status="SUCCESS",
                result=result,
                finished_at=timezone.now(),
            )
            logger.info(
                "parse_rup_with_llm_task FALLBACK SUCCESS task_id=%s items=%s",
                task_id,
                len(result),
            )
        except Exception as fallback_exc:
            logger.error(
                "parse_rup_with_llm_task FALLBACK FAILED task_id=%s error=%s",
                task_id,
                fallback_exc,
            )
            RupParseTask.objects.filter(pk=task_id).update(
                status="FAILURE",
                error=str(fallback_exc),
                finished_at=timezone.now(),
            )


def _llm_parse(file_bytes: bytes, filename: str) -> list:
    text = _extract_text(file_bytes, filename)
    if not text.strip():
        raise ValueError("Could not extract text from file")

    prompt = (
        "Ты — ИИ-ассистент учебной части университета.\n"
        "Извлеки из учебного плана (РУП) список дисциплин и верни ТОЛЬКО валидный JSON массив.\n"
        "Каждый элемент: name (строка), credits (число), lec, prac, srsp, srs (часы, числа), "
        "type (REQUIRED или ELECTIVE).\n\n"
        f"Текст учебного плана:\n{text[:3000]}\n\n"
        "Верни ТОЛЬКО JSON массив без markdown и пояснений. Пример:\n"
        '[{"name": "Математика", "credits": 5, "lec": 32, "prac": 16, "srsp": 16, "srs": 32, "type": "REQUIRED"}]'
    )

    payload = {
        "model": "gemma3:4b",
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.05, "num_predict": 2048},
    }

    resp = requests.post(_OLLAMA_URL, json=payload, timeout=_LLM_TIMEOUT)
    resp.raise_for_status()
    raw = resp.json().get("response", "")
    return _extract_json_list(raw)


def _algorithmic_parse(file_bytes: bytes, filename: str) -> list:
    from io import BytesIO

    from schedule.services import RupImporter

    file_obj = BytesIO(file_bytes)
    file_obj.name = filename
    return RupImporter.parse_for_preview(file_obj)


def _extract_text(file_bytes: bytes, filename: str) -> str:
    from io import BytesIO

    name = filename.lower()
    if name.endswith(".pdf"):
        import pdfplumber

        text = ""
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages[:10]:
                text += (page.extract_text() or "") + "\n"
        return text
    elif name.endswith((".xlsx", ".xls")):
        import openpyxl

        wb = openpyxl.load_workbook(BytesIO(file_bytes), data_only=True)
        sheet = wb.active
        rows = []
        for row in sheet.iter_rows(min_row=1, max_row=60, values_only=True):
            rows.append(" | ".join([str(c) if c is not None else "" for c in row]))
        return "\n".join(rows)
    raise ValueError(f"Unsupported file type: {filename}")


def _extract_json_list(raw: str) -> list:
    match = re.search(r"\[[\s\S]*\]", raw)
    if match:
        return json.loads(match.group(0))
    raise ValueError("No JSON array found in LLM response")


def start_parse_task(task_id: str, file_bytes: bytes, filename: str) -> None:
    t = threading.Thread(
        target=parse_rup_with_llm_task,
        args=(task_id, file_bytes, filename),
        daemon=True,
        name=f"rup_parse_{task_id[:8]}",
    )
    t.start()
    logger.info("start_parse_task: thread started task_id=%s filename=%s", task_id, filename)