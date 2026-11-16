"""School permissions: one catalog shared by API validation and the role editor."""
import re

PERMISSIONS = [
    {"key": "dashboard.view", "group": "متابعة المدرسة", "label": "عرض لوحة اليوم", "description": "إحصاءات المدرسة والتكليفات وحمولة المعلمين."},
    {"key": "assistant.use", "group": "متابعة المدرسة", "label": "استخدام المساعد المدرسي", "description": "طرح أسئلة عن بيانات المدرسة التي تسمح بها صلاحيات الحساب."},
    {"key": "directory.view", "group": "المعلمون والجدول", "label": "عرض المعلمين والمواد والشعب", "description": "قراءة دليل المدرسة."},
    {"key": "directory.edit", "group": "المعلمون والجدول", "label": "إدارة المعلمين والمواد والشعب", "description": "إضافة البيانات وتعديل المعلمين وإيقافهم."},
    {"key": "schedule.view", "group": "المعلمون والجدول", "label": "عرض جدول المدرسة", "description": "عرض وطباعة حصص جميع المعلمين."},
    {"key": "schedule.edit", "group": "المعلمون والجدول", "label": "تعديل الحصص", "description": "إضافة حصص الجدول وتعديلها وحذفها."},
    {"key": "schedule.import", "group": "المعلمون والجدول", "label": "استيراد الجدول", "description": "استيراد ملف وقد يستبدل الجدول وقائمة المعلمين الحالية."},
    {"key": "absences.manage", "group": "الغياب والاحتياط", "label": "تسجيل الغياب", "description": "قراءة الغياب وتسجيله للحصص المتأثرة."},
    {"key": "substitutions.view", "group": "الغياب والاحتياط", "label": "عرض تكليفات المدرسة", "description": "الاطلاع على سجل الاحتياط لكل المعلمين."},
    {"key": "substitutions.manage", "group": "الغياب والاحتياط", "label": "إدارة التكليفات", "description": "اقتراح البدلاء وإسناد الحصص وتأكيدها وإنهاؤها وإلغاؤها."},
    {"key": "reports.view", "group": "التقارير والإعدادات", "label": "عرض وطباعة التقارير", "description": "تقارير الاحتياط اليومية لجميع المعلمين."},
    {"key": "audit.view", "group": "التقارير والإعدادات", "label": "عرض سجل التدقيق", "description": "قراءة الإجراءات المنفذة وأسماء منفذيها."},
    {"key": "settings.manage", "group": "التقارير والإعدادات", "label": "تعديل هوية المدرسة", "description": "تغيير اسم المدرسة وشعار الطباعة."},
]
PERMISSION_KEYS = {item["key"] for item in PERMISSIONS}
DEPENDENCIES = {
    "directory.edit": {"directory.view"},
    "schedule.view": {"directory.view"},
    "schedule.edit": {"schedule.view"},
    "schedule.import": {"schedule.edit", "directory.edit"},
    "absences.manage": {"schedule.view", "substitutions.view"},
    "substitutions.manage": {"substitutions.view", "schedule.view"},
}


def expand_permissions(keys):
    result = set(keys) & PERMISSION_KEYS
    while True:
        expanded = result | set().union(*(DEPENDENCIES.get(key, set()) for key in result))
        if expanded == result:
            return sorted(result)
        result = expanded


BUILTIN_ROLES = {
    "TEACHER": {"name": "معلم", "permissions": ["assistant.use"]},
    "COORDINATOR": {"name": "منسق", "permissions": expand_permissions([
        "dashboard.view", "assistant.use", "schedule.view", "absences.manage", "substitutions.manage", "reports.view", "audit.view",
    ])},
}


def account_access(account):
    from .models import AdminAccount
    if isinstance(account, AdminAccount):
        return {"role": "MANAGER", "role_name": "مدير المدرسة", "permissions": sorted(PERMISSION_KEYS)}
    if account.role == "CUSTOM":
        role = account.custom_role
        # Fail closed even if a malformed foreign-school reference exists.
        if not role or role.school_id != account.school_id:
            return {"role": "CUSTOM", "role_name": "دور غير متاح", "permissions": []}
        return {"role": "CUSTOM", "role_name": role.name, "permissions": expand_permissions(role.permissions)}
    role = BUILTIN_ROLES.get(account.role, {"name": "معلم", "permissions": []})
    return {"role": account.role, "role_name": role["name"], "permissions": role["permissions"]}


def required_permission(method, path):
    """Return a permission for known routes only. Unknown routes are denied to staff."""
    if method == "GET":
        if re.fullmatch(r"/api/(teachers(?:/\d+)?|subjects|classes)", path):
            return "directory.view"
        if path == "/api/schedule":
            return "schedule.view"
        if re.fullmatch(r"/api/absences(?:/\d+)?", path):
            return "absences.manage"
        if path == "/api/substitutions":
            return "substitutions.view"
        if path in {"/api/dashboard/today", "/api/dashboard/overview"}:
            return "dashboard.view"
        if path == "/api/reports/daily-substitutions":
            return "reports.view"
        if path == "/api/audit":
            return "audit.view"
    if method == "POST":
        if path == "/api/assistant/chat":
            return "assistant.use"
        if path in {"/api/teachers", "/api/subjects", "/api/classes"}:
            return "directory.edit"
        if path in {"/api/schedule/import-file", "/api/schedule/import-csv"}:
            return "schedule.import"
        if path == "/api/schedule":
            return "schedule.edit"
        if path == "/api/absences":
            return "absences.manage"
        if path == "/api/substitutions/suggest" or re.fullmatch(r"/api/substitutions/\d+/(assign|confirm|complete|cancel)", path):
            return "substitutions.manage"
    if method in {"PUT", "DELETE"}:
        if re.fullmatch(r"/api/teachers/\d+", path):
            return "directory.edit"
        if re.fullmatch(r"/api/schedule/\d+", path):
            return "schedule.edit"
    if method == "PUT" and path == "/api/school-settings":
        return "settings.manage"
    return None
