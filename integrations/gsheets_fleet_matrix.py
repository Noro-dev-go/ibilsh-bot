# integrations/gsheets_fleet_matrix.py
import os, json, re, io
from datetime import datetime, date
from typing import Dict, Any, Optional, Tuple, List

import gspread
from google.oauth2.service_account import Credentials
from google.auth.exceptions import TransportError
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials as UserCredentials

from gspread.exceptions import APIError


import time
import requests

from pathlib import Path
from dotenv import load_dotenv


def _retry(fn, tries: int = 4, base_delay: float = 0.8, what: str = ""):
    """
    Выполняет fn() с ретраями и экспоненциальной паузой.
    Перехватывает типичные сетевые ошибки Google/Requests.
    """
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except (requests.exceptions.RequestException, TransportError, HttpError, APIError) as e:
            if attempt == tries:
                raise
            # опционально лог:
            # print(f"[retry:{what}] attempt {attempt}/{tries} failed: {e}")
            time.sleep(base_delay * (2 ** (attempt - 1)))


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



def _google_credentials():
    """
    Возвращает google.auth.credentials.Credentials (нужен для Drive API).
    """
    _ensure_env_loaded()
    sa_path = os.getenv("GOOGLE_SA_JSON")
    if sa_path and os.path.exists(sa_path):
        return Credentials.from_service_account_file(sa_path, scopes=SCOPES)
    content = os.getenv("GOOGLE_SA_JSON_CONTENT")
    if not content:
        raise RuntimeError("No Google SA credentials provided")
    return Credentials.from_service_account_info(json.loads(content), scopes=SCOPES)

def _auth():
    _ensure_env_loaded()
    sa_path = os.getenv("GOOGLE_SA_JSON")
    if sa_path and os.path.exists(sa_path):
        creds = _google_credentials()
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
    return _retry(lambda: _auth().open_by_key(sid).sheet1, what="open sheet1")

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


NEW_ROW_MAP = {
    "Номер транс.": 2,
    "ФИО": 3,
    "Модель": 4,
    "Дата выдачи": 5,
    "Тег в тг": 6,
    "Номер тел.": 7,
    "Проект": 8,
    "Основной склад": 9,
    "Договор": 10,
    "Заметки": 11,
}

# Начало зоны "журнала оплат" и финблока (подгони при необходимости)
NEW_DATE_ROWS_START = 12
NEW_DATE_ROWS_END = 63
NEW_COST_BLOCK_TOP  = 105

def _ws_and_next_empty_col(sheet_id: Optional[str] = None):
    ws = _ws(sheet_id)
    # ищем по строке "Номер транс." (строка 2)
    row_vals = ws.row_values(NEW_ROW_MAP["Номер транс."])
    last = len(row_vals)
    # начинаем новую ПАРУ так, чтобы слева был ДАТНЫЙ столбец
    base_col = 1 if last == 0 else (last + 2 if last % 2 == 1 else last + 1)
    return ws, base_col

def _ws_and_next_empty_pair(sheet_id: Optional[str] = None):
    ws = _ws(sheet_id)
    # ориентируемся по строке "Номер транс." — она заполняется только в ЛЕВОМ столбце пары
    vals = ws.row_values(NEW_ROW_MAP["Номер транс."])
    last_main_col = len(vals)  # индекс последнего заполненного основного столбца
    # размещаем новую пару через ОДИН пустой столбец: [main][sums][SPACER] -> следующий main
    left_col = 1 if last_main_col == 0 else last_main_col + 3
    return ws, left_col



def _next_transport_number(ws) -> int:
    import re
    vals = ws.row_values(NEW_ROW_MAP["Номер транс."])
    nums = []
    for v in vals:
        s = re.sub(r"\D+", "", str(v))
        if s:
            try:
                nums.append(int(s))
            except:
                pass
    return (max(nums) + 1) if nums else 1

def _col(n: int) -> str:
    return _col_letter(n)

def generate_fridays_2025():
    from datetime import date, timedelta
    d = date(2025, 1, 3)
    last = date(2025, 12, 26)
    while d <= last:
        yield d
        d += timedelta(days=7)

def _apply_new_design(ws, left_col: int):
    sheet_id = ws.id
    svc = sheets_service()
    reqs = []

    # жёлтый фон для дат (левый столбец пары)
    reqs.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": NEW_DATE_ROWS_START - 1,
                "endRowIndex":   NEW_DATE_ROWS_END,
                "startColumnIndex": left_col - 1,
                "endColumnIndex":   left_col,
            },
            "cell": {"userEnteredFormat": {
                "backgroundColor": COLOR_YELLOW,
                "horizontalAlignment": "CENTER"
            }},
            "fields": "userEnteredFormat(backgroundColor,horizontalAlignment)"
        }
    })
    # лейблы финблока (в левом)
    reqs.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": NEW_COST_BLOCK_TOP - 1,
                "endRowIndex":   NEW_COST_BLOCK_TOP + 2,
                "startColumnIndex": left_col - 1,
                "endColumnIndex":   left_col,
            },
            "cell": {"userEnteredFormat": {"backgroundColor": COLOR_ORANGE}},
            "fields": "userEnteredFormat(backgroundColor)"
        }
    })
    # «Стоимость» (значение) — зелёным в правом
    reqs.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": NEW_COST_BLOCK_TOP - 1,
                "endRowIndex":   NEW_COST_BLOCK_TOP,
                "startColumnIndex": left_col,
                "endColumnIndex":   left_col + 1,
            },
            "cell": {"userEnteredFormat": {"backgroundColor": COLOR_GREEN}},
            "fields": "userEnteredFormat(backgroundColor)"
        }
    })
    svc.spreadsheets().batchUpdate(spreadsheetId=ws.spreadsheet.id, body={"requests": reqs}).execute()


def create_client_column_auto(
    payload: dict, *, transport_number: str | None = None,
    project_name: str | None = "Самокат", sheet_id: Optional[str] = None,
) -> tuple[int, str]:
    ws, left_col = _ws_and_next_empty_pair(sheet_id)
    mainL = _col(left_col)           # левый: номер + шапка + даты
    sumsL = _col(left_col + 1)       # правый: суммы/значения

    # Номер транс. — в ЭТОМ ЖЕ (левом) столбце, строка 2
    number_to_set = transport_number or str(_next_transport_number(ws))
    _retry(lambda: ws.update_acell(f"{mainL}{NEW_ROW_MAP['Номер транс.']}", number_to_set),
           what="set transport number")

    # Шапка (3..11) — тоже в левом столбце
    header_rows = [
        [payload.get("ФИО") or ""],
        [payload.get("Модель") or ""],
        [_fmt_date(payload.get("Дата выдачи"))],
        [payload.get("Тег в тг") or ""],
        [payload.get("Номер тел.") or ""],
        [project_name or ""],
        [payload.get("Основной склад") or ""],
        ["✅" if payload.get("Договор") else "❌"],
        [payload.get("Заметки") or ""],
    ]
    _retry(lambda: ws.update(f"{mainL}{NEW_ROW_MAP['ФИО']}:{mainL}{NEW_ROW_MAP['Заметки']}",
                             header_rows, value_input_option="RAW"),
           what="update header")

    # Даты (12..63) — в левом столбце под шапкой
    rows = [[d.strftime("%d.%m.%Y")] for d in generate_fridays_2025()]
    _retry(lambda: ws.update(f"{mainL}{NEW_DATE_ROWS_START}:{mainL}{NEW_DATE_ROWS_END}",
                             rows, value_input_option="RAW"),
           what="seed dates")

    # Финблок: лейблы в левом, значения в правом
    cost = int(payload.get("Стоимость") or 0)
    block = [
        ["Стоимость",        cost],
        ["Зашло:",           0],
        ["Траты ремонта:",   0],
        ["Ремонт (дата/стоимость)", ""],
    ]
    _retry(lambda: ws.update(f"{mainL}{NEW_COST_BLOCK_TOP}:{sumsL}{NEW_COST_BLOCK_TOP+3}",
                             block, value_input_option="RAW"),
           what="cost block")

    # Формула «Зашло:» суммирует правый столбец (суммы) за 12..63
    _retry(lambda: ws.update_acell(f"{sumsL}{NEW_COST_BLOCK_TOP+1}",
                                   f"=SUM({sumsL}{NEW_DATE_ROWS_START}:{sumsL}{NEW_DATE_ROWS_END})"),
           what="inflow formula")

    _apply_new_design(ws, left_col)   # оформляем левый датный столбец
    return left_col, mainL            # возвращаем индекс ОСНОВНОГО столбца


def record_payment_new_layout(left_group_col: int, amount: int, paid_date: datetime, *, sheet_id: Optional[str]=None, also_increment_inflow: bool=False) -> tuple[bool, str]:
    ws = _ws(sheet_id)
    main_col = left_group_col                 # даты здесь
    sums_col = left_group_col + 1             # суммы здесь

    rng = _retry(lambda: ws.get(f"{_col(main_col)}{NEW_DATE_ROWS_START}:{_col(main_col)}{NEW_DATE_ROWS_END}"),
                 what="get dates range")
    target = paid_date.strftime("%d.%m.%Y")
    row_idx = next((i for i, row in enumerate(rng, start=NEW_DATE_ROWS_START) if row and row[0].strip()==target), None)
    if not row_idx:
        return False, f"Дата {target} не найдена (12..63)."

    cell_amount = f"{_col(sums_col)}{row_idx}"
    cur = _to_number(_retry(lambda: ws.acell(cell_amount).value, what="read amount"))
    _retry(lambda: ws.update_acell(cell_amount, str(cur + int(amount))), what="write amount")
    return True, f"Оплата {amount} ₽ записана в {cell_amount}."

# --- Фото и ремонтный блок (заготовки) ---

def sheets_service():
    try:
        from googleapiclient.discovery import build
    except ImportError as e:
        raise RuntimeError(
            "Не установлен google-api-python-client. "
            "pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        ) from e
    return build("sheets", "v4", credentials=_google_credentials())

# палитра
COLOR_YELLOW = {"red": 1.0, "green": 0.9, "blue": 0.6}
COLOR_ORANGE = {"red": 1.0, "green": 0.75, "blue": 0.0}
COLOR_GREEN  = {"red": 0.8, "green": 0.92, "blue": 0.7}


def _user_oauth_creds():
    """
    Берём токен пользователя (drive_user_token.json), чтобы писать в личный/общий диск.
    """
    _ensure_env_loaded()
    token_path = os.getenv("DRIVE_OAUTH_TOKEN")
    if not token_path or not os.path.exists(token_path):
        return None
    # токен сгенерирован bootstrap-скриптом; в нём уже есть refresh_token
    return UserCredentials.from_authorized_user_file(token_path, SCOPES)


def upload_image_bytes_to_drive(
    image_bytes: bytes,
    file_name: str,
    folder_id: Optional[str] = None,
) -> str:
    """
    Загружает картинку в Google Drive и возвращает публичный URL для =IMAGE(...).
    Работает и с Общими дисками (Shared Drives), если у аккаунта есть права.
    Требует, чтобы drive_service() возвращал сервис с корректными кредами
    (желательно пользовательский OAuth).
    """
    try:
        from googleapiclient.http import MediaIoBaseUpload
    except ImportError as e:
        raise RuntimeError(
            "google-api-python-client не установлен. "
            "pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        ) from e

    drv = drive_service()

    # Кто мы (для отладки; поле 'user' содержит emailAddress/displayName)
    try:
        who = drv.about().get(fields="user").execute()
        print("[DRIVE] whoami:", who.get("user", {}))
    except Exception as e:
        raise RuntimeError(f"Drive 'about' failed: {e}")

    media = MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype="image/jpeg", resumable=False)

    body = {"name": file_name}
    dest_folder = folder_id or os.getenv("DRIVE_FOLDER_ID")
    if dest_folder:
        body["parents"] = [dest_folder]

    try:
        # ВАЖНО: supportsAllDrives=True для загрузки в Общий диск
        f = drv.files().create(
            body=body,
            media_body=media,
            fields="id,parents,name",
            supportsAllDrives=True,
        ).execute()
    except HttpError as e:
        raise RuntimeError(f"Drive create failed: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Drive create failed (generic): {e}") from e

    file_id = f["id"]

    # Попробуем сделать файл доступным по ссылке (в доменных политиках может быть запрещено)
    try:
        drv.permissions().create(
            fileId=file_id,
            body={"role": "reader", "type": "anyone"},
            supportsAllDrives=True,
        ).execute()
    except HttpError as e:
        # Не критично для Общего диска; просто предупреждение
        print("[DRIVE] set public permission warning:", e)
    except Exception:
        pass

    # Прямой URL, который подходит для формулы =IMAGE("...")
    return f"https://drive.google.com/uc?id={file_id}"



def _add_image_over_cells(ws, sheet_id_int: int, row: int, col: int, url: str,
                          width_px: int, height_px: int):
    """Вставляет картинку как 'over cells' (манипулируемую)."""
    svc = sheets_service()
    req = {
        "requests": [{
            "addImage": {
                "image": {"sourceUri": url},
                "anchorCell": {
                    "sheetId": sheet_id_int,
                    "rowIndex": row - 1,        # 0-based
                    "columnIndex": col - 1
                },
                "offsetXPixels": 0,
                "offsetYPixels": 0,
                "widthPixels":  width_px,
                "heightPixels": height_px
            }
        }]
    }
    svc.spreadsheets().batchUpdate(
        spreadsheetId=ws.spreadsheet.id,
        body=req
    ).execute()


def place_client_photos(left_group_col: int, url1: str, url2: str, url3: str, *, sheet_id: Optional[str]=None, width_px: int=480, height_px: int=360):
    ws = _ws(sheet_id)
    colA1 = _col(left_group_col)              # под основным столбцом
    base_row = NEW_DATE_ROWS_END + 2
    rows = [base_row, base_row + 18, base_row + 36]
    sheet_gid = ws.id

    svc = sheets_service()
    reqs = [{
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_gid, "dimension": "COLUMNS",
                      "startIndex": left_group_col - 1, "endIndex": left_group_col},
            "properties": {"pixelSize": width_px}, "fields": "pixelSize"
        }
    }]
    for r in rows:
        reqs.append({
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_gid, "dimension": "ROWS",
                          "startIndex": r - 1, "endIndex": r},
                "properties": {"pixelSize": height_px}, "fields": "pixelSize"
            }
        })
    svc.spreadsheets().batchUpdate(spreadsheetId=ws.spreadsheet.id, body={"requests": reqs}).execute()

    # локаль RU -> ;  и режим 4 (кастомный размер)
    f = lambda u: f'=IMAGE("{u}";4;{height_px};{width_px})'
    ws.update(f"{colA1}{rows[0]}", [[f(url1)]], value_input_option="USER_ENTERED")
    ws.update(f"{colA1}{rows[1]}", [[f(url2)]], value_input_option="USER_ENTERED")
    ws.update(f"{colA1}{rows[2]}", [[f(url3)]], value_input_option="USER_ENTERED")



def drive_service():
    """
    Пытаемся использовать пользовательский OAuth (для личного/общего диска).
    Если токена нет — падаем обратно на креды сервис-аккаунта.
    """
    from googleapiclient.discovery import build
    user_creds = _user_oauth_creds()
    if user_creds:
        return build("drive", "v3", credentials=user_creds)
    # fallback: сервис-аккаунт
    return build("drive", "v3", credentials=_google_credentials())

def insert_image_from_url(col_index: int, row: int, url: str, *, sheet_id: Optional[str] = None):
    ws = _ws(sheet_id)
    ws.update_acell(f"{_col(col_index)}{row}", f'=IMAGE("{url}")')

def set_cost_value(left_group_col: int, cost: int, *, sheet_id: Optional[str] = None):
    ws = _ws(sheet_id)
    sumsL = _col(left_group_col + 1)
    _retry(lambda: ws.update_acell(f"{sumsL}{NEW_COST_BLOCK_TOP}", str(int(cost or 0))), what="set_cost_value")

def add_repair_cost(col_index: int, amount: int, note: str = "", *, sheet_id: Optional[str] = None):
    ws = _ws(sheet_id)
    baseL = _col(col_index)
    # Накапливаем «Траты ремо»
    cell = f"{baseL}{NEW_COST_BLOCK_TOP+2}"
    cur = _to_number(ws.acell(cell).value)
    ws.update_acell(cell, str(cur + int(amount)))
    # лог строкой ниже блока
    r = NEW_COST_BLOCK_TOP + 4
    while ws.acell(f"{baseL}{r}").value:
        r += 1
    ws.update_acell(f"{baseL}{r}", f"{_fmt_date(datetime.now())} / {amount} — {note}")