"""
rup_parser.py v2 — Точный позиционный парсер РУП для Таджикистана.

Изменения v2:
  - Аудиторные кредиты (AP) делятся 50/50 на lec + prac (ceil/floor).
    Причина: в таджикском РУП "Аудиторӣ" = лекции + практика (суммарно).
    Разбивка 50/50 — стандартная пропорция; пользователь корректирует в UI.
  - primary_semester корректно устанавливается из exam_semesters.
  - Формат вывода 100% совместим с import_rup_excel view.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Dict, List, Tuple

import openpyxl
from openpyxl.utils import column_index_from_string

logger = logging.getLogger(__name__)






def _ci(letter: str) -> int:
    return column_index_from_string(letter)


def _safe_int(val) -> int:
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).strip()
    if not s or s.lower() in ('none', 'null', '-', '—', 'нет'):
        return 0
    m = re.search(r'\d+', s)
    return int(m.group()) if m else 0


def _parse_sem_list(val) -> List[int]:
    """
    '3'         → [3]
    '3,4,5'     → [3, 4, 5]
    '3.3'       → [3]       (Tajik notation: semester 3, block 3)
    '3,4,5,5,6' → [3, 4, 5, 6]  (dedup, sorted)
    None / ''   → []
    """
    if val is None:
        return []
    s = str(val).strip()
    if not s or s.lower() in ('none', 'null', '-', '—'):
        return []
    nums: List[int] = []
    seen: set = set()
    for part in re.split(r'[,;\s/]+', s):
        part = part.strip()
        m = re.match(r'^(\d+)', part)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 8 and n not in seen:
                nums.append(n)
                seen.add(n)
    return sorted(nums)


def _clean(val) -> str:
    if val is None:
        return ''
    return re.sub(r'\s+', ' ', str(val)).strip().strip('"\'«»\n\r')


def _row_vals(ws, row_num: int) -> Dict[int, Any]:
    return {cell.column: cell.value
            for cell in ws[row_num]
            if cell.value is not None}


def _split_auditory(aud: int) -> Tuple[int, int]:
    """
    Split total auditory credits into (lecture, practice).

    Tajik RUP "Аудиторӣ" = lecture credits + practice credits combined.
    Standard split: ceil/floor (larger half → lectures).

    Examples:
      aud=2 → lec=1, prac=1
      aud=3 → lec=2, prac=1
      aud=4 → lec=2, prac=2
      aud=0 → lec=0, prac=0
    """
    if aud <= 0:
        return 0, 0
    lec = math.ceil(aud / 2)
    prac = aud - lec
    return lec, prac






_SEM_COLS = {
    1: _ci('AZ'), 2: _ci('BB'), 3: _ci('BD'), 4: _ci('BF'),
    5: _ci('BH'), 6: _ci('BJ'), 7: _ci('BL'), 8: _ci('BN'),
}


_S1 = dict(
    name      = _ci('B'),
    credits   = _ci('W'),
    exam      = _ci('AC'),
    cw        = _ci('AI'),
    active    = _ci('AL'),
    aud       = _ci('AP'),
    kmro      = _ci('AT'),
    kmd       = _ci('AW'),
    sem       = _SEM_COLS,
    data_start= 31,
    data_end  = 79,
)


_S2 = dict(
    name      = _ci('C'),
    credits   = _ci('X'),
    exam      = _ci('AD'),
    cw        = _ci('AI'),
    active    = _ci('AL'),
    aud       = _ci('AP'),
    kmro      = _ci('AT'),
    kmd       = _ci('AW'),
    sem       = _SEM_COLS,
    data_start= 7,
    data_end  = 33,
)






_SECTION_STARTS = ('бахши', 'аттестатсияи')
_MODULE_STARTS  = ('модули',)
_SKIP_CONTAINS  = ('ҳамагӣ', 'хамаги', 'итого', 'всего')


def _classify(name: str) -> str:
    n = name.lower().strip()
    if not n:
        return 'skip'
    if any(kw in n for kw in _SKIP_CONTAINS):
        return 'skip'
    if any(n.startswith(kw) for kw in _SECTION_STARTS):
        return 'section'
    if any(n.startswith(kw) for kw in _MODULE_STARTS):
        return 'module'
    return 'subject'


def _section_disc_type(section_name: str) -> str:
    n = section_name.upper()
    if any(kw in n for kw in ('ИНТИХОБӢ', 'ИНТИХОБИ', 'ВЫБОРОЧН')):
        return 'ELECTIVE'
    if any(kw in n for kw in ('ТАҶРИБА', 'ТАЧРИБА', 'ПРАКТИК')):
        return 'PRACTICE'
    if any(kw in n for kw in ('АТТЕСТАТСИЯ', 'ХАТМ')):
        return 'GRADUATION'
    return 'REQUIRED'






class RupParser:
    def __init__(self, src):
        self.wb = openpyxl.load_workbook(src, data_only=True)
        self.disciplines: List[Dict] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self._counter = 0

    def parse(self) -> List[Dict]:
        self.disciplines.clear()
        self.errors.clear()
        self.warnings.clear()
        self._counter = 0

        self._parse_main(self.wb.worksheets[0])

        if len(self.wb.worksheets) > 1:
            self._parse_electives(self.wb.worksheets[1])
        else:
            self.warnings.append("Sheet 2 not found — elective disciplines skipped.")

        logger.info(
            "RupParser: %d disciplines | %d errors | %d warnings",
            len(self.disciplines), len(self.errors), len(self.warnings),
        )
        return self.disciplines

    

    def _parse_main(self, ws):
        cols = _S1
        sec_name = ''
        sec_type = 'REQUIRED'
        mod_name = ''

        for r in range(cols['data_start'], cols['data_end'] + 1):
            rv   = _row_vals(ws, r)
            name = _clean(rv.get(cols['name']))
            if not name:
                continue

            cls = _classify(name)
            if cls == 'skip':
                continue
            if cls == 'section':
                sec_name = name
                sec_type = _section_disc_type(name)
                mod_name = ''
                continue
            if cls == 'module':
                mod_name = re.sub(r'^[Мм]одули\s+', '', name).strip()
                continue

            
            credits = _safe_int(rv.get(cols['credits']))
            if not credits and rv.get(cols['aud']) is None and rv.get(cols['credits']) is None:
                self.warnings.append(f"Sheet1 row {r}: '{name}' — no data, skipped.")
                continue

            self.disciplines.append(self._build(
                name=name, rv=rv, cols=cols,
                disc_type=sec_type, sec=sec_name, mod=mod_name,
                slot_id='', alts=[],
            ))

    

    def _parse_electives(self, ws):
        cols = _S2
        mod_name = ''

        rows: List[Tuple] = []
        for r in range(cols['data_start'], cols['data_end'] + 1):
            rv   = _row_vals(ws, r)
            raw  = rv.get(cols['name'])
            if raw is None:
                continue
            name = _clean(raw)
            if not name:
                continue
            a_val = rv.get(1)
            rows.append((r, a_val, name, rv))

        i = 0
        while i < len(rows):
            r, a_val, name, rv = rows[i]

            if _classify(name) == 'skip':
                i += 1
                continue
            if _classify(name) == 'module':
                mod_name = re.sub(r'^[Мм]одули\s+', '', name).strip()
                i += 1
                continue

            credits  = _safe_int(rv.get(cols['credits']))
            has_data = credits > 0 or rv.get(cols['aud']) is not None

            if not has_data:
                self.warnings.append(f"Sheet2 row {r}: '{name}' — no data, skipped.")
                i += 1
                continue

            slot_id = str(a_val).strip() if a_val is not None else ''
            alts: List[str] = []
            j = i + 1
            while j < len(rows):
                _, _, nxt_name, nxt_rv = rows[j]
                nxt_credits  = _safe_int(nxt_rv.get(cols['credits']))
                nxt_has_data = nxt_credits > 0 or nxt_rv.get(cols['aud']) is not None
                if nxt_has_data:
                    break
                if _classify(nxt_name) in ('module', 'section', 'skip'):
                    break
                alts.append(nxt_name)
                j += 1

            self.disciplines.append(self._build(
                name=name, rv=rv, cols=cols,
                disc_type='ELECTIVE', sec='Фанҳои интихобӣ', mod=mod_name,
                slot_id=slot_id, alts=alts,
            ))
            i = j

    

    def _build(
        self,
        name: str, rv: Dict, cols: Dict,
        disc_type: str, sec: str, mod: str,
        slot_id: str, alts: List[str],
    ) -> Dict:
        self._counter += 1

        credits = _safe_int(rv.get(cols['credits']))
        active  = _safe_int(rv.get(cols['active']))
        aud     = _safe_int(rv.get(cols['aud']))
        kmro    = _safe_int(rv.get(cols['kmro']))
        kmd     = _safe_int(rv.get(cols['kmd']))

        exam_sems = _parse_sem_list(rv.get(cols['exam']))
        cw_sems   = _parse_sem_list(rv.get(cols['cw']))

        sem_creds: Dict[int, int] = {
            s: _safe_int(rv.get(ci)) for s, ci in cols['sem'].items()
        }

        
        primary_sem = (
            exam_sems[0] if exam_sems
            else next((s for s in range(1, 9) if sem_creds.get(s, 0) > 0), 0)
        )

        
        
        
        
        lec, prac = _split_auditory(aud)
        srsp = kmro
        srs  = kmd

        try:
            from schedule.models import SubjectTemplate
            is_new = not SubjectTemplate.objects.filter(name__iexact=name).exists()
        except Exception:
            is_new = True

        return {
            
            'id':                   self._counter,
            'name':                 name,
            'type':                 disc_type,          

            
            'credits':              credits,
            'active_credits':       active,
            'auditory':             aud,                
            'kmro':                 kmro,
            'kmd':                  kmd,

            
            'lec':                  lec,                
            'prac':                 prac,               
            'srsp':                 srsp,               
            'srs':                  srs,                

            
            'exam_semesters':       exam_sems,
            'coursework_semesters': cw_sems,
            'semester_credits':     sem_creds,
            'primary_semester':     primary_sem,        

            
            'section_name':         sec,
            'module_name':          mod,
            'is_aggregate':         False,
            'is_new_template':      is_new,

            
            'elective_slot_id':     slot_id,
            'alternatives':         alts,
        }


def parse_rup_file(filepath_or_fileobj) -> List[Dict]:
    try:
        parser = RupParser(filepath_or_fileobj)
        return parser.parse()
    except Exception as exc:
        logger.exception("parse_rup_file failed")
        raise ValueError(f"Не удалось разобрать файл РУП: {exc}") from exc