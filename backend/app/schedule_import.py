"""Read common school timetable CSV/XLSX layouts into normalized schedule cells."""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException


@dataclass(frozen=True)
class ScheduleCell:
    teacher: str
    day: str
    period: int
    status: str
    class_name: str | None
    subject: str | None
    notes: str | None = None


DAY_ALIASES = {
    "sunday": "SUNDAY", "sun": "SUNDAY", "الأحد": "SUNDAY", "الاحد": "SUNDAY",
    "monday": "MONDAY", "mon": "MONDAY", "الإثنين": "MONDAY", "الاثنين": "MONDAY", "الإثنين": "MONDAY",
    "tuesday": "TUESDAY", "tue": "TUESDAY", "الثلاثاء": "TUESDAY",
    "wednesday": "WEDNESDAY", "wed": "WEDNESDAY", "الأربعاء": "WEDNESDAY", "الاربعاء": "WEDNESDAY",
    "thursday": "THURSDAY", "thu": "THURSDAY", "الخميس": "THURSDAY",
}
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).translate(_DIGITS).strip()
    return re.sub(r"\s+", " ", text)


def _compact(value: Any) -> str:
    return re.sub(r"[\W_]", "", _text(value).casefold(), flags=re.UNICODE)


def _day(value: Any) -> str | None:
    text = _text(value).casefold()
    for alias, day in DAY_ALIASES.items():
        if alias.casefold() in text:
            return day
    return None


def _period(value: Any) -> int | None:
    text = _text(value)
    match = re.search(r"(?<!\d)([1-7])(?!\d)", text)
    return int(match.group(1)) if match else None


def _field(value: Any) -> str | None:
    key = _compact(value)
    aliases = {
        "teacher": {"teacher", "teachername", "name", "اسم المعلم", "المعلم", "اسم الأستاذ", "اسم الاستاذ", "المعلم/ة"},
        "subject": {"subject", "specialization", "التخصص", "المادة", "المادة/التخصص"},
        "day": {"day", "dayofweek", "weekday", "اليوم"},
        "period": {"period", "periodnumber", "رقم الحصة", "الحصة", "رقم الفترة"},
        "status": {"status", "cellstatus", "الحالة", "نوع الحصة"},
        "class": {"class", "section", "classname", "classnumber", "sectionnumber", "class/section", "الشعبة", "رقم الشعبة", "الفصل", "رقم الفصل", "الصف", "الصف/الشعبة"},
        "notes": {"notes", "note", "ملاحظات", "ملاحظة"},
    }
    for canonical, choices in aliases.items():
        if key in {_compact(choice) for choice in choices}:
            return canonical
    return None


def _load_rows(filename: str, content: bytes) -> list[list[Any]]:
    suffix = Path(filename or "").suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise HTTPException(500, "دعم Excel غير مثبت؛ ثبّت openpyxl ثم أعد تشغيل الخادم") from exc
        try:
            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            sheet = next((s for s in workbook.worksheets if s.max_row and s.max_column), None)
            if sheet is None:
                raise HTTPException(400, "ملف Excel لا يحتوي جدولًا")
            return [list(row) for row in sheet.iter_rows(values_only=True)]
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, "تعذر قراءة ملف Excel؛ استخدم ملف XLSX صالحًا") from exc
    if suffix != ".csv":
        raise HTTPException(400, "الصيغ المدعومة هي CSV وExcel XLSX")
    decoded = None
    for encoding in ("utf-8-sig", "utf-8", "cp1256"):
        try:
            decoded = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        raise HTTPException(400, "تعذر قراءة ترميز CSV؛ احفظه بترميز UTF-8")
    sample = decoded[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [list(row) for row in csv.reader(io.StringIO(decoded), dialect)]


def _find_headers(rows: list[list[Any]]) -> tuple[int, list[tuple[str | None, str | None, str | None]]]:
    """Return header row index and per-column (field, day, period) mapping."""
    for index in range(min(5, len(rows))):
        row = rows[index]
        fields = [_field(value) for value in row]
        if "teacher" not in fields:
            continue
        mapping: list[tuple[str | None, str | None, str | None]] = []
        detected_periods = 0
        for value, field in zip(row, fields):
            day = _day(value)
            period = _period(value)
            if day and period:
                mapping.append((None, day, str(period)))
                detected_periods += 1
            elif field:
                mapping.append((field, None, None))
            else:
                mapping.append((None, None, None))
        # Excel often has merged weekday headings on row 1 and period numbers on row 2.
        if index + 1 < len(rows):
            lower = rows[index + 1]
            inherited_day = None
            for col in range(max(len(row), len(lower))):
                top = row[col] if col < len(row) else None
                bottom = lower[col] if col < len(lower) else None
                top_day = _day(top)
                if top_day:
                    inherited_day = top_day
                lower_period = _period(bottom)
                if inherited_day and lower_period and _field(top) is None:
                    while len(mapping) <= col:
                        mapping.append((None, None, None))
                    mapping[col] = (None, inherited_day, str(lower_period))
                    detected_periods += 1
                elif _field(top):
                    while len(mapping) <= col:
                        mapping.append((None, None, None))
                    mapping[col] = (_field(top), None, None)
            if detected_periods:
                return index, mapping
        if detected_periods:
            return index, mapping
        # Wide daily CSV: teacher, specialization, day, period_1 ... period_7.
        period_columns = sum(1 for value in row if re.search(r"(?:period|الحصة).*?[1-7]|[1-7].*(?:period|الحصة)", _text(value), re.I))
        if "day" in fields and period_columns:
            for col, value in enumerate(row):
                match = re.search(r"(?:period|الحصة).*?([1-7])|([1-7]).*(?:period|الحصة)", _text(value), re.I)
                if match:
                    number = next(group for group in match.groups() if group)
                    mapping[col] = (None, None, number)
            return index, mapping
        if "day" in fields:
            return index, [(field, None, None) for field in fields]
    raise HTTPException(400, "لم أتعرف على عناوين الجدول. ارفع ملفًا يحتوي اسم المعلم واليوم والحصة، أو أعمدة أيام وحصص واضحة.")


def _status(value: Any, supplied_status: Any = None) -> tuple[str, str | None]:
    raw = _text(value)
    explicit = _text(supplied_status).upper()
    aliases = {"TEACHING": "TEACHING", "تدريس": "TEACHING", "درس": "TEACHING",
               "FREE": "FREE", "فراغ": "FREE", "حرة": "FREE", "متاح": "FREE",
               "DUTY": "DUTY", "مناوبة": "DUTY", "احتياط": "DUTY", "ح": "DUTY",
               "OTHER": "OTHER", "أخرى": "OTHER", "اخرى": "OTHER"}
    if explicit:
        mapped = aliases.get(explicit)
        if not mapped:
            raise ValueError(f"حالة غير معروفة: {explicit}")
        if mapped == "FREE":
            return mapped, None
        return mapped, raw or None
    marker = raw.casefold()
    if marker in {"", "-", "—", "free", "فراغ", "حرة", "متاح"}:
        return "FREE", None
    if marker in {"ح", "احتياط", "مناوبة", "duty"}:
        return "DUTY", None
    return "TEACHING", raw


def parse_schedule_file(filename: str, content: bytes) -> tuple[list[ScheduleCell], str]:
    rows = _load_rows(filename, content)
    header_index, mapping = _find_headers(rows)
    header_fields = {field: index for index, (field, _, _) in enumerate(mapping) if field}
    wide_columns = [(index, day, int(period)) for index, (_, day, period) in enumerate(mapping) if day and period]
    # Support a teacher/day row with الحصة_1 .. الحصة_7 columns.
    if not wide_columns and "day" in header_fields:
        header = rows[header_index]
        for col, value in enumerate(header):
            match = re.search(r"(?:period|الحصة).*?([1-7])|([1-7]).*(?:period|الحصة)", _text(value), re.I)
            if match:
                number = int(next(group for group in match.groups() if group))
                wide_columns.append((col, None, number))
    output: list[ScheduleCell] = []
    last_subject = ""
    for row_number, row in enumerate(rows[header_index + 1:], start=header_index + 2):
        if not any(_text(value) for value in row):
            continue
        def get(field: str) -> str:
            col = header_fields.get(field)
            return _text(row[col]) if col is not None and col < len(row) else ""
        teacher = get("teacher")
        if not teacher:
            # Ignore title/notes rows above or below the actual teacher table.
            continue
        subject = get("subject")
        if subject:
            last_subject = subject
        elif last_subject:
            subject = last_subject
        if wide_columns:
            day_field = get("day")
            for col, fixed_day, period in wide_columns:
                day = fixed_day or _day(day_field)
                if not day:
                    raise HTTPException(400, f"تعذر تحديد اليوم في صف {row_number}")
                value = row[col] if col < len(row) else None
                try:
                    status, class_name = _status(value, get("status"))
                except ValueError as exc:
                    raise HTTPException(400, f"صف {row_number}: {exc}") from exc
                output.append(ScheduleCell(teacher, day, period, status, class_name, subject or None, get("notes") or None))
        else:
            day = _day(get("day"))
            period = _period(get("period"))
            if not day or not period:
                raise HTTPException(400, f"تعذر تحديد اليوم أو الحصة في صف {row_number}")
            try:
                status, class_name = _status(get("class"), get("status"))
            except ValueError as exc:
                raise HTTPException(400, f"صف {row_number}: {exc}") from exc
            output.append(ScheduleCell(teacher, day, period, status, class_name, subject or None, get("notes") or None))
    if not output:
        raise HTTPException(400, "الملف لا يحتوي حصصًا قابلة للاستيراد")
    return output, "wide" if wide_columns else "long"
