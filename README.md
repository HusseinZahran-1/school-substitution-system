# نظام إدارة جدول الاحتياط المدرسي الآلي

تطبيق عربي لإدارة جدول المعلمين الأسبوعي، تسجيل الغياب، اقتراح بديل متاح بناءً على الجدول الفعلي، وتوثيق التقارير الإلكترونية اليومية.

> **مصدر الجدول:** الملف الممسوح `Scanned Document.pdf` هو المرجع للمعلمين والشُعب والحصص. لا تُستخدم قائمة المعلمين التجريبية كمصدر للبيانات. كل خلية تُراجع من الملف قبل اعتمادها؛ لا تُخمن الخانات غير الواضحة.

## الوظائف

- إدارة المعلمين والمواد والشعب، مع تخصص متعدد لكل معلم.
- جدول أسبوعي منطقي: معلم + يوم + حصة + شعبة + مادة + حالة (`TEACHING`, `FREE`, `DUTY`, `OTHER`).
- شاشة دخول للإدارة مع إنشاء حساب أول مرة، وتخزين كلمة المرور بتجزئة PBKDF2 وجلسة موقعة في Cookie محمية.
- عرض خلايا المعلمين لكل يوم، تعديل الخلايا، واستيراد Excel XLSX أو CSV بالعناوين العربية والإنجليزية.
- لوحة جاهزية للجدول تعرض اكتمال الحصص، وعدد المعلمين والمواد والشعب والفترات الحرة، مع بحث وتصفية حسب حالة الجدول.
- إنشاء المعلمين والتخصصات والشُعب تلقائيًا من الملف، مع استبدال اختياري للبيانات الحالية وحفظ ذري عند نجاح التحقق.
- تسجيل غياب معلم لحصة واحدة أو أكثر، واكتشاف الفصل والمادة من الجدول.
- اقتراح مرتب بعد استبعاد الغائب والمعلمين غير النشطين والمشغولين أو المكلفين باحتياط متعارض.
- شرح أهلية المرشح وسبب ترتيبه، مع خطوة منفصلة لتأكيد الاختيار أو اختيار بديل يدويًا.
- حالة التكليف وسجل تدقيق وحمولة يومية وتقارير إلكترونية حسب التاريخ.
- طباعة ورقية للجدول الأسبوعي والتقرير اليومي بتنسيق A4 أفقي.
- PostgreSQL للإنتاج وSQLite افتراضيًا للتشغيل المحلي السريع.

## تحليل الجدول وتصميم البيانات

التمثيل المنطقي هو جدول `schedule_entries`، لا صورة الورقة نفسها. لكل معلم خانة واحدة كحد أقصى في اليوم والحصة (`UNIQUE(teacher_id, day_of_week, period_number)`). تحفظ الخانة الفصل والمادة وحالتها. لذا تظل الفترات الحرة صريحة في المصدر، ويُشترط وجود سجل `FREE` حتى يدخل المعلم قائمة المرشحين. لا يعتبر غياب السجل دليلاً على التوفر.

المواد منفصلة في `subjects` وترتبط بالمعلمين بعلاقة متعدد إلى متعدد. الشعب مستقلة في `classes`. يسجل `absences` غياب اليوم، وتسجل `absence_periods` الحصص المطلوبة، ويربط كل تكليف في `substitution_assignments` بالغياب والفصل والمعلمين والحالة والموقع والملاحظات والتوقيع. يضمن قيد قاعدة البيانات `UNIQUE(date, period_number, substitute_teacher_id)` عدم تكليف معلم مرتين في الفترة نفسها. يحفظ `audit_logs` تغييرات إنشاء/إسناد/تأكيد/إكمال/إلغاء التكليف.

يدعم المستورد صفوف CSV الطويلة (`teacher,day,period,status,class,subject`) والجداول العريضة التي تحتوي أعمدة `الحصة_1` إلى `الحصة_7` مع عمود اليوم، وكذلك ملفات XLSX ذات عناوين الأيام والفترات. الخانة الفارغة في الجدول العريض تُسجل `FREE`، والرمز `ح` أو كلمة «احتياط» تُسجل `DUTY`، وقيم الشُعب مثل `1/2` تُسجل `TEACHING`. تُعرض تعارضات المعلم المكررة بدل تخمين الاختيار.

## منطق الترشيح

1. التحقق من المعلم الغائب النشط واليوم والحصة والحصة التدريسية في الجدول (أو تحديد شعبة يدويًا إذا كان الجدول ناقصًا).
2. تحديد المرشحين داخل SQL من المعلمين النشطين الذين لديهم خانة `FREE` صريحة في اليوم والحصة نفسها.
3. استبعاد المعلم الغائب، كل معلم لديه خانة غير `FREE` في الوقت نفسه، وكل معلم له إسناد فعلي في اليوم والحصة.
4. ترتيب المرشحين حتميًا حسب: مطابقة التخصص، قلة تكليفات اليوم، قلة التكليفات التاريخية، ثم رقم المعلم. لا تدخل الاقتراحات غير المؤكدة في عداد الحمل.
5. عرض القائمة والأسباب قبل الإسناد. يعيد النظام نتيجة صريحة بلا مرشحين بدل اختيار غير متاح.
6. عند الإسناد يعاد التحقق من التوفر ويطبق قيد uniqueness داخل المعاملة. ينتج عن سباق الإسناد تعارض `409` بدل تكليف مزدوج.

ترتيب التخصص قبل عداد الحمل يعكس أولوية الترتيب الواردة في قواعد العمل؛ التوفر يظل قيدًا قطعيًا قبل أي تفضيل.

## التقنيات والبنية

- Backend: Python 3.12+, FastAPI, SQLAlchemy 2, Pydantic 2, Alembic.
- Database: PostgreSQL 16 عبر `psycopg`; SQLite للاستخدام المحلي والاختبارات.
- Frontend: HTML/CSS/JavaScript دون إطار عمل، عربية RTL.
- أول زيارة تعرض إعداد حساب المدير، وبعدها تتطلب الواجهة وواجهات API تسجيل الدخول.

```text
backend/app/{api.py,engine.py,models.py,schemas.py,core.py,database.py,security.py,schedule_import.py,main.py}
backend/alembic/                 migrations
frontend/index.html              واجهة الإدارة
frontend/assets/{css,js}/        التنسيق والتفاعل
tests/                           اختبارات قواعد العمل
docker-compose.yml               PostgreSQL + API
```

## تشغيل Windows محليًا

من PowerShell:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

يعمل SQLite محليًا تلقائيًا إذا لم تعدل `DATABASE_URL`. أنشئ المخطط وشغّل الخادم:

```powershell
alembic upgrade head
uvicorn app.main:app --reload --port 8001
```

يمكن أيضًا تشغيله من مجلد `backend` مباشرةً باستخدام `python app/main.py`؛ سيبدأ الخادم على `http://127.0.0.1:8001`.

```powershell
$env:PORT = "8002"
python app/main.py
```

أو شغّل Uvicorn مباشرةً: `uvicorn app.main:app --reload --port 8002`.

افتح http://localhost:8001 للواجهة أو http://localhost:8001/docs لتوثيق OpenAPI.

### PostgreSQL محليًا

أنشئ قاعدة PostgreSQL ومستخدمًا، ثم عدل `backend/.env`:

```env
DATABASE_URL=postgresql+psycopg://school_admin:YOUR_PASSWORD@localhost:5432/school_substitution
CORS_ORIGINS=http://localhost:8001
SCHOOL_TIMEZONE=Asia/Amman
SESSION_SECRET=<random-long-secret>
```

نفّذ `alembic upgrade head` ثم شغّل Uvicorn كما أعلاه.

## Docker Compose

أنشئ ملف `.env` في جذر المشروع، ولا تضعه في Git:

```env
POSTGRES_DB=school_substitution
POSTGRES_USER=school_admin
POSTGRES_PASSWORD=choose_a_long_random_password
CORS_ORIGINS=http://localhost:8001
APP_PORT=8001
SCHOOL_TIMEZONE=Asia/Amman
SESSION_SECRET=<random-long-secret>
```

ثم:

```powershell
docker compose up --build
```

الخادم يطبق ترحيلات Alembic عند البدء. الواجهة متاحة على `http://localhost:8001` افتراضيًا؛ غيّر `APP_PORT` إذا كان المنفذ مستخدمًا. البيانات دائمة في volume `postgres_data`.

## تجهيز بيانات المدرسة

1. أنشئ حساب المدير عند فتح التطبيق لأول مرة.
2. افتح «الجدول الأسبوعي»، اختر XLSX أو CSV، ثم «قراءة واستيراد تلقائي».
3. خيار استبدال البيانات مفعّل افتراضيًا؛ راجع اسم الملف والتأكيد قبل الاستيراد. يحتفظ النظام بسجلات الغياب والتكليف القديمة ويعطل المعلمين القدامى فقط إذا كانت لهم سجلات تاريخية.
4. لا تبدأ تسجيل الغياب قبل التأكد من أن الملف يحتوي تدريسًا وفترات فراغ صحيحة؛ لا يعتبر غياب الخانة دليلًا على التوفر.

CSV UTF-8 يقبل الأعمدة الإلزامية `teacher,day,period,status` والاختيارية `class,subject,notes`:

```csv
teacher,day,period,status,class,subject,notes
محمد الشياب,THURSDAY,3,TEACHING,2/ب,اللغة العربية,
خالد العتيبي,THURSDAY,3,FREE,,,
```

ينشئ المستورد المعلم والمادة والشعبة تلقائيًا. يتحقق من تكرار الخانات والتعارضات قبل الحفظ، وعند فشل التحقق لا يحفظ جزءًا من الملف. يقبل كذلك جدول CSV العريض مثل `التخصص,اسم المعلم,اليوم,الحصة_1,...,الحصة_7`.

## API مختصر

- `GET/POST /api/teachers`, `GET/PUT/DELETE /api/teachers/{id}`
- `GET/POST /api/subjects`, `GET/POST /api/classes`
- `GET/POST /api/schedule`, `PUT/DELETE /api/schedule/{id}`, `POST /api/schedule/import-file` (CSV/XLSX)
- `POST /api/absences`, `GET /api/absences`
- `POST /api/substitutions/suggest` returns ranked candidates without confirming an assignment
- `GET /api/substitutions?on_date=YYYY-MM-DD`
- `POST /api/substitutions/{id}/assign`, `/confirm`, `/complete`, `/cancel`
- `GET /api/dashboard/today`, `GET /api/dashboard/overview`, `GET /api/reports/daily-substitutions?on_date=YYYY-MM-DD`
- `POST /api/auth/setup`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/status`
- `GET /api/audit`, `GET /api/health`

مثال تسجيل غياب:

```json
{
  "teacher_id": 12,
  "date": "2026-09-24",
  "reason": "إجازة",
  "created_by": "مدير النظام",
  "periods": [{"period_number": 3}]
}
```

الاستجابة تتضمن `day`, الفصل والمادة المكتشفين، `recommended_substitute`, القائمة المرتبة وأسبابها. إذا تعذر الترشيح تكون `candidates: []` و`recommended_substitute: null`. بعد المراجعة:

```json
{"substitute_teacher_id": 18, "waiting_location": "المكتبة", "approved_by": "مدير النظام"}
```

## التقارير الإلكترونية

افتح «التقارير الإلكترونية» وحدد التاريخ لعرض الحصص المتأثرة، الفصل، المعلم الغائب، البديل، الحالة، موقع الانتظار والملاحظات. استخدم «طباعة التقرير» أو «طباعة الجدول» لطباعة نسخة A4 أفقية. غيّر اسم المدرسة الافتراضي في `backend/app/api.py` إلى الاسم الفعلي.

## الاختبارات

من جذر المشروع بعد تثبيت `backend/requirements.txt`:

```powershell
python -m pytest
```

تغطي الاختبارات تحويل اليوم، رفض عطلة نهاية الأسبوع، قيد الفراغ الصريح، استبعاد المشغول والغائب وغير النشط والمكلف، المطابقة والتوازن، عدم وجود مرشح، وقيدي تكرار الجدول والإسناد.

## تحسينات مستقبلية

إدارة عدة مديرين، إعدادات متعددة المدارس، عطلات وجداول استثنائية، إشعارات، تسجيل توقيع رقمي، إحصاءات، تصدير PDF، وتحسين متزامن لعدة حصص. قاعدة البيانات تفصل الجداول والغياب والتكليفات بما يسمح بالتوسع دون تغيير معنى الخانة الأسبوعية.
