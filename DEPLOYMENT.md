# تجهيز ونشر النظام على Hostinger Web Hosting + خادم API

> **تنبيه توافق:** Hostinger Web Hosting يستطيع استضافة واجهة الموقع الثابتة فقط. لا يشغّل FastAPI/Python أو PostgreSQL، لذلك لا يكفي رفع المشروع كاملًا إلى `public_html`. Hostinger يذكر أن PostgreSQL غير متاح على Web/Cloud hosting وأن تطبيقات Python تحتاج VPS. هذا الإعداد يضع الواجهة على Web Hosting والـAPI مع PostgreSQL على VPS أو خدمة أخرى تدعم Docker وPostgreSQL. [تفاصيل PostgreSQL](https://support.hostinger.com/en/articles/1583659-is-postgresql-supported-at-hostinger) · [تفاصيل Python](https://support.hostinger.com/en/articles/1583678-is-django-supported-at-hostinger)

## إعداد واجهة Hostinger Web Hosting

1. اختر نطاق الموقع، مثل `school.example.com`، واجعل DNS الخاص به يشير إلى Hostinger.
2. ارفع **محتويات** مجلد `frontend` إلى مجلد `public_html`، بحيث يصبح `index.html` مباشرة داخله، ومعه `config.js` ومجلد `assets`.
3. قبل الرفع، انسخ `config.hostinger.example.js` إلى `config.js`، ثم غيّر `apiBaseUrl` إلى عنوان HTTPS الفعلي للـAPI، مثل `https://api.school.example.com`.
4. شغّل إعداد خادم الـAPI وقاعدة البيانات أدناه على VPS. اجعل `DOMAIN=api.school.example.com`، وأضف سجل DNS من نوع `A` للاسم `api` يشير إلى عنوان الـVPS.
5. في `.env.production`، اضبط `CORS_ORIGINS` على أصل الواجهة كما يظهر في شريط العنوان، مثل `https://school.example.com`. إذا كان الموقع يعمل أيضًا بعنوان `www`, أضف الأصلين مفصولين بفاصلة. لا تضع مسارًا مثل `/api` هنا.
6. اضبط `PUBLIC_APP_URL` على عنوان واجهة المستخدم (`https://school.example.com`) ليستخدمه رابط دعوة الموظف عبر البريد.
7. تأكد أن شهادة HTTPS صالحة للنطاقين، ثم افتح واجهة Hostinger وسجّل الدخول. الجلسات تعمل عبر `api` subdomain على النطاق نفسه؛ لا تستخدم عنوان API من نطاق منفصل.

لا تنسخ مجلد `backend` إلى `public_html`؛ رفع كود Python هناك لا يشغّله. ملفات الواجهة ثابتة وجاهزة للرفع، لكن خصائص الحسابات والبيانات لن تعمل قبل نشر الـAPI وضبط DNS و`config.js` و`CORS_ORIGINS`. إذا كان الدومين لم يُحسم بعد، اترك `frontend/config.js` كما هو للتشغيل المحلي، وأكمل الاستبدال على نسخة النشر بعد اختيار الدومين.

## إعداد خادم الـAPI وقاعدة البيانات

هذا الإعداد يشغّل التطبيق وPostgreSQL داخل Docker، ويضع Caddy أمام التطبيق لإصدار وتجديد شهادة HTTPS تلقائيًا. قاعدة البيانات لا تفتح منفذًا عامًا، وواجهة التطبيق تصل إليها فقط عبر الوكيل.

## المتطلبات

- خادم Ubuntu أو Debian حديث مع Docker Engine وDocker Compose plugin.
- اسم نطاق تملكه، مع سجلي DNS من النوع `A` يشيران إلى عنوان IPv4 للخادم. أضف سجل `AAAA` فقط إذا كان IPv6 مضبوطًا على الخادم.
- السماح لاتصالات TCP على المنفذين 80 و443 في جدار الحماية ولوحة شركة الاستضافة. افتح UDP 443 اختياريًا لـ HTTP/3.
- بيانات SMTP فعالة قبل السماح بالتسجيل الذاتي؛ البريد مطلوب لإرسال مفاتيح التفعيل.

## الإعداد الأول

ارفع ملفات المشروع إلى الخادم، ثم من مجلد المشروع:

```sh
cp .env.production.example .env.production
```

عدّل `.env.production`:

- ضع اسم النطاق في `DOMAIN` من دون `https://`.
- ولّد قيمًا مختلفة لكل من `POSTGRES_PASSWORD` و`SESSION_SECRET` و`LICENSE_HASH_SECRET` باستخدام `openssl rand -hex 32`.
- أضف بيانات SMTP الحقيقية. لا ترفع `.env.production` إلى Git ولا ترسل محتواه لأحد.
- اضبط `PUBLIC_APP_URL` على عنوان واجهة Hostinger الكامل؛ يستخدمه المدير لدعوة المنسقين والمعلمين. تأكد أن خادم البريد يسمح بالاتصال الصادر قبل إرسال الدعوات.
- اترك `REGISTRATION_ENABLED=false` حتى تضبط SMTP وتكون جاهزًا للتسجيل العام. بعد تفعيله، ينشئ كل تسجيل مدرسة مستقلة وحساب إدارة خاصًا بها؛ الجداول والمعلمون والتقارير والإعدادات معزولة بين المدارس.

تأكد أن DNS يشير إلى الخادم وأن المنافذ 80 و443 متاحة، ثم شغّل:

```sh
docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
```

خدمة Ollama تعمل داخل شبكة Docker الخاصة بالخادم ولا تفتح منفذًا عامًا. بعد أول تشغيل، حمّل النموذج المحلي مرة واحدة:

```sh
docker compose --env-file .env.production -f docker-compose.production.yml exec ollama ollama pull qwen2.5-coder:7b
```

النموذج الافتراضي حجمه نحو 4.7GB على القرص، ويحتاج ذاكرة مناسبة أثناء التشغيل. يمكن اختيار وسم نموذج آخر عبر `OLLAMA_MODEL` في `.env.production` قبل التشغيل، ويجب تحميل الوسم نفسه داخل حاوية Ollama. لا يحتاج المساعد إلى مفتاح API؛ الطلب والبيانات يذهبان إلى Ollama على نفس الخادم عبر شبكة Docker الداخلية. إذا كنت تشغل الـAPI مباشرة على Windows، اترك `OLLAMA_BASE_URL=http://127.0.0.1:11434`، واختر `qwen2.5-coder:7b` الموجود محليًا.

تحقق من سلامة الحاويات والسجلات:

```sh
docker compose --env-file .env.production -f docker-compose.production.yml ps
docker compose --env-file .env.production -f docker-compose.production.yml logs --tail=100 backend caddy
curl -fsS "https://$(grep '^DOMAIN=' .env.production | cut -d= -f2-)/healthz"
```

عند نجاح التهيئة، افتح `https://اسم-النطاق/`. لا تستخدم عنوان IP بدل اسم النطاق؛ إصدار شهادة HTTPS يتطلب DNS صحيحًا.

## إنشاء حساب المدير الأول

بعد ظهور حالة `healthy` لخدمة `backend`، أنشئ حساب المدير داخل الحاوية. كلمة المرور تُطلب تفاعليًا ولا تُحفظ في سجل الأوامر:

```sh
docker compose --env-file .env.production -f docker-compose.production.yml exec backend python -m app.provision_admin
```

يسمح الأمر بإنشاء حساب bootstrap واحد فقط، ويمنحه ترخيصًا نشطًا. بعدها سجّل الدخول من الموقع. لا يحتاج هذا الحساب إلى إرسال مفتاح تفعيل بالبريد. يبقى التسجيل العام مغلقًا في الإعداد الافتراضي.

## التحديثات

احتفظ بنسخة احتياطية قبل كل تحديث، ثم ارفع الكود الجديد وشغّل:

```sh
docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
```

تُطبّق ترحيلات Alembic عند تشغيل التطبيق. لا تحذف volume قاعدة البيانات عند التحديث، ولا تستخدم `down -v`.

## النسخ الاحتياطي والاستعادة

أنشئ نسخة متسقة من PostgreSQL:

```sh
sh deploy/backup.sh
```

انقل النسخ الناتجة دوريًا إلى تخزين منفصل عن الخادم. ملف النسخة وحده لا يكفي لاستعادة تسجيل الدخول: احتفظ أيضًا بنسخة آمنة من `.env.production`، وخصوصًا `SESSION_SECRET` و`LICENSE_HASH_SECRET`.

لاستعادة ملف dump إلى قاعدة فارغة، أوقف التطبيق أولًا، ثم نفّذ الأمر مع اختيار ملف النسخة:

```sh
docker compose --env-file .env.production -f docker-compose.production.yml stop backend
cat ./backups/FILE.dump | docker compose --env-file .env.production -f docker-compose.production.yml exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists'
docker compose --env-file .env.production -f docker-compose.production.yml up -d
```

أمر الاستعادة يستبدل الجداول الموجودة؛ تحقّق من ملف النسخة قبل تشغيله.

## إعداد البريد والتسجيل

إعدادات SMTP موجودة في `.env.production`. بعد تغييرها أعد إنشاء خدمة التطبيق:

```sh
docker compose --env-file .env.production -f docker-compose.production.yml up -d --force-recreate backend
```

بعد تجهيز SMTP، اضبط `REGISTRATION_ENABLED=true` إذا أردت استقبال مدارس جديدة. كل حساب مسجل ينشئ مساحة مدرسة جديدة مستقلة ويحتاج مفتاح ترخيص خاصًا به. الحسابات والبيانات الموجودة قبل ترقية العزل تُحفظ ضمن مدرسة "المدرسة الحالية" واحدة؛ إذا كانت هناك حسابات قديمة متعددة فقد تظل مرتبطة بهذه البيانات القديمة المشتركة، لأن النظام لا يملك معلومات تحدد المدرسة المالكة لكل سجل سابق.

## فحوصات التشغيل

- حالة التطبيق وقاعدة البيانات: `https://اسم-النطاق/healthz`.
- سجل بدء التطبيق: `docker compose --env-file .env.production -f docker-compose.production.yml logs -f backend`.
- نسخة قاعدة البيانات: `sh deploy/backup.sh` ثم انقل الملف إلى مكان منفصل.
- تاريخ انتهاء TLS وتجديده يديرهما Caddy تلقائيًا ما دام DNS والمنفذان 80 و443 متاحين.

## حدود النشر

- يمكن لنسخة التطبيق وقاعدة PostgreSQL واحدة استضافة مدارس متعددة؛ تُربط كل مدرسة بحسابها وتُفلتر عمليات القراءة والكتابة حسب المدرسة الحالية.
- ملفات الجدول المدعومة هي DOCX (جدول المعلمين الأسبوعي)، CSV وXLSX؛ خانات ح1 ثم ح2 إلى ح5 تتقدم على الفراغ العادي عند ترشيح البديل.
- لم يتم ربط اسم نطاق أو حساب استضافة من هذا المستودع؛ يلزم ضبط DNS والجدار الناري لدى مزودك.

## تحديث الأدوار المخصصة

عند إعادة تشغيل الباك إند، يطبق Alembic الترحيل `0009_custom_roles` تلقائيًا. يضيف جدول الأدوار وعلاقتها بالموظفين ويحافظ على الحسابات والأدوار الحالية. انشر ملفات الواجهة مع الباك إند، بما فيها `assets/js/roles.js`، حتى تظهر إدارة الصلاحيات. في التشغيل بعدة نسخ، نفّذ الترحيل مرة واحدة قبل تحديث النسخ.

اختبارات الصلاحيات وعزل المدارس: `python -m pytest tests/test_roles.py -q`. تستخدم الاختبارات قاعدة معزولة ولا تحتاج إرسال بريد حقيقي.
