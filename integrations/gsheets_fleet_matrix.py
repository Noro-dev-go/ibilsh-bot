# integrations/gsheets_fleet_matrix.py
import os, json, re
from datetime import datetime, date
from typing import Dict, Any, Optional, Tuple, List

import gspread
from google.oauth2.service_account import Credentials

from pathlib import Path
from dotenv import load_dotenv

def _ensure_env_loaded():
    """
    Грузим .env только если нужных переменных ещё нет.
    И одновременно поддерживаем старое имя переменной GOOGLE_SHEET_ID.
    """
    need_sa = not (os.getenv("GOOGLE_SA_JSON") or os.getenv("GOOGLE_SA_JSON_CONTENT"))
    need_sheet = not (os.getenv("GOOGLE_SHEET_RENT_ID") or os.getenv("GOOGLE_SHEET_ID"))
    if need_sa or need_sheet:
        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# соответствие "название строки -> номер строки" в верхней части таблицы
ROW_MAP = {
    "Номер транс.": 2,
    "Стоимость аренды в н-ю.": 3,
    "Дата введения в эксплуатацию": 4,
    "Начальная стоимость": 5,
    "Зашло": 6,
    "Модель транспорта 1/2 АКБ": 7,
    "Вин номер рамы": 8,
    "Вин номер мотора": 9,
    "Вин номер АКБ#1": 10,
    "Вин номер АКБ#2": 11,
    "Наличие GPS": 12,
    "Дата выдачи": 13,
    "ФИО арендатора": 14,
    "Тег арендатора": 15,
    "Номер арендатора": 16,
    "Место работы": 17,
    "Основной склад": 18,
    "Наличие договора": 19,
    "Заметки": 20,
    "Сумма": 21,
}

# Диапазон «журнала оплат» (нижняя часть, где жёлтые даты)
DATE_ROWS_START = 40
DATE_ROWS_END = 400

def _auth():
    _ensure_env_loaded()
    sa_path = os.getenv("GOOGLE_SA_JSON")
    if sa_path and os.path.exists(sa_path):
        creds = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
    else:
        content = os.getenv("GOOGLE_SA_JSON_CONTENT")
        if not content:
            raise RuntimeError("No Google SA credentials provided")
        creds = Credentials.from_service_account_info(json.loads(content), scopes=SCOPES)
    return gspread.authorize(creds)

def _ws(sheet_id: Optional[str] = None):
    _ensure_env_loaded()
    sid = sheet_id or os.getenv("GOOGLE_SHEET_RENT_ID")
    if not sid:
        raise RuntimeError("GOOGLE_SHEET_RENT_ID not set")
    return _auth().open_by_key(sid).sheet1

def _col_letter(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s

def _fmt_date(v):
    if not v: return ""
    if isinstance(v, (datetime, date)):
        return v.strftime("%d.%m.%Y")
    try:
        return datetime.fromisoformat(str(v)).strftime("%d.%m.%Y")
    except Exception:
        return str(v)

def _fmt_bool(v):
    s = str(v).strip().lower()
    if s in {"1","true","да","yes","y","истина"}: return "да"
    if s in {"0","false","нет","no","n","ложь",""}: return "нет"
    return str(v)

def _to_number(s) -> int:
    if s is None: return 0
    s = str(s).strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
    try:
        return int(float(re.sub(r"[^\d.\-]", "", s)))
    except Exception:
        return 0

def upsert_by_column_index(
    col_index: int,
    data: Dict[str, Any],
    *,
    increment_deposit: Optional[int] = None,
    set_transport_number: Optional[str] = None,
    sheet_id: Optional[str] = None,
):
    """
    Пишем/обновляем вертикальный столбец по заданному номеру колонки (1-based).
    increment_deposit — добавить сумму в 'Зашло'.
    set_transport_number — если передано, проставим в 'Номер транс.' (обычно это просто номер колонки).
    """
    ws = _ws(sheet_id)
    col_letter = _col_letter(col_index)
    start, end = min(ROW_MAP.values()), max(ROW_MAP.values())

    # текущие значения (чтобы не затирать незаполненные поля)
    current = {}
    rng = ws.get(f"{col_letter}{start}:{col_letter}{end}")
    for label, i in ROW_MAP.items():
        idx = i - start
        current[label] = (rng[idx][0] if idx < len(rng) and rng[idx] else "")

    # инкремент 'Зашло'
    if increment_deposit is not None:
        already = _to_number(current.get("Зашло"))
        data["Зашло"] = already + int(increment_deposit)

    values = {
        "Номер транс.": set_transport_number if set_transport_number is not None else current.get("Номер транс."),
        "Стоимость аренды в н-ю.": data.get("Стоимость аренды в н-ю.", current.get("Стоимость аренды в н-ю.")),
        "Дата введения в эксплуатацию": _fmt_date(data.get("Дата введения в эксплуатацию") or current.get("Дата введения в эксплуатацию")),
        "Начальная стоимость": data.get("Начальная стоимость", current.get("Начальная стоимость")),
        "Зашло": data.get("Зашло", current.get("Зашло")),
        "Модель транспорта 1/2 АКБ": data.get("Модель транспорта 1/2 АКБ", current.get("Модель транспорта 1/2 АКБ")),
        "Вин номер рамы": data.get("Вин номер рамы", current.get("Вин номер рамы")),
        "Вин номер мотора": data.get("Вин номер мотора", current.get("Вин номер мотора")),
        "Вин номер АКБ#1": data.get("Вин номер АКБ#1", current.get("Вин номер АКБ#1") or "нет"),
        "Вин номер АКБ#2": data.get("Вин номер АКБ#2", current.get("Вин номер АКБ#2") or "нет"),
        "Наличие GPS": _fmt_bool(data.get("Наличие GPS")) if "Наличие GPS" in data else (current.get("Наличие GPS") or "нет"),
        "Дата выдачи": _fmt_date(data.get("Дата выдачи") or current.get("Дата выдачи")),
        "ФИО арендатора": data.get("ФИО арендатора", current.get("ФИО арендатора")),
        "Тег арендатора": data.get("Тег арендатора", current.get("Тег арендатора")),
        "Номер арендатора": data.get("Номер арендатора", current.get("Номер арендатора")),
        "Место работы": data.get("Место работы", current.get("Место работы")),
        "Основной склад": data.get("Основной склад", current.get("Основной склад")),
        "Наличие договора": _fmt_bool(data.get("Наличие договора")) if "Наличие договора" in data else (current.get("Наличие договора") or "нет"),
        "Заметки": data.get("Заметки", current.get("Заметки")),
        "Сумма": data.get("Сумма", data.get("Стоимость аренды в н-ю.") or current.get("Сумма")),
    }

    ordered = [[values[key]] for key in ROW_MAP.keys()]
    ws.update(f"{col_letter}{start}:{col_letter}{end}", ordered, value_input_option="RAW")

# ===== НИЖНИЙ «ЖУРНАЛ ОПЛАТ» =====

def _parse_date(s: str) -> Optional[datetime]:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None

def _find_date_column_near(ws, base_col: int, max_offset: int = 8) -> Optional[int]:
    # ищем столбец, где много валидных дат
    for col in range(base_col, base_col + max_offset + 1):
        col_letter = _col_letter(col)
        rng = ws.get(f"{col_letter}{DATE_ROWS_START}:{col_letter}{DATE_ROWS_END}")
        cnt = 0
        for row in rng:
            if row and _parse_date(row[0]):
                cnt += 1
        if cnt >= 5:
            return col
    return None

def _find_row_by_date(ws, date_col: int, paid_dt: datetime) -> Optional[int]:
    target = paid_dt.strftime("%d.%m.%Y")
    col_letter = _col_letter(date_col)
    rng = ws.get(f"{col_letter}{DATE_ROWS_START}:{col_letter}{DATE_ROWS_END}")
    for idx, row in enumerate(rng):
        if (row and row[0].strip()) == target:
            return DATE_ROWS_START + idx
    return None

def find_column_by_transport_number(transport_label: str, sheet_id: Optional[str] = None) -> Optional[int]:
    """
    Ищет колонку по значению в строке 'Номер транс.'.
    Принимает: '35', 'H35', 'h35' — всё матчит.
    Возвращает 1-based индекс столбца или None.
    """
    ws = _ws(sheet_id)
    target_raw = (transport_label or "").strip()
    if not target_raw:
        return None

    # разрешаем формы: '35', 'H35', 'h35'
    num_only = re.sub(r"\D+", "", target_raw)
    candidates = {target_raw, target_raw.upper(), target_raw.lower()}
    if num_only:
        candidates.update({num_only, f"H{num_only}", f"h{num_only}"})

    row_idx = ROW_MAP["Номер транс."]
    row_vals = ws.row_values(row_idx)

    for idx, val in enumerate(row_vals, start=1):
        if str(val).strip() in candidates:
            return idx
    return None

def record_payment(
    base_col_index: int,
    amount: int,
    paid_date: datetime,
    *,
    date_col_index: Optional[int] = None,
    also_increment_deposit: bool = True,
    sheet_id: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Пишет сумму в журнал (левая ячейка от даты) и, опционально, инкрементит 'Зашло'.
    """
    ws = _ws(sheet_id)

    dates_col = date_col_index or _find_date_column_near(ws, base_col_index)
    if not dates_col:
        return False, f"Не нашёл столбец с датами рядом с колонкой {base_col_index}"

    row_idx = _find_row_by_date(ws, dates_col, paid_date)
    if not row_idx:
        return False, f"Дата {paid_date.strftime('%d.%m.%Y')} не найдена (колонка дат {dates_col})"

    amount_col = dates_col - 1
    if amount_col < 1:
        return False, "Левая колонка для суммы недоступна"

    cell = f"{_col_letter(amount_col)}{row_idx}"
    current_val = ws.acell(cell).value
    new_val = _to_number(current_val) + int(amount)
    ws.update_acell(cell, str(new_val))

    if also_increment_deposit:
        upsert_by_column_index(
            base_col_index,
            data={},
            increment_deposit=amount,
            sheet_id=sheet_id,
        )

    return True, f"Оплата {amount} ₽ записана в {cell}; 'Зашло' обновлено."
