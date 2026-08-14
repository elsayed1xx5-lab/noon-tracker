# Noon Egypt Sales Tracker 🔥

نظام يومي يراقب المبيعات على نون مصر. الرقم الأساسي: **sold recently** لكل منتج.

---

## 🚀 أسرع طريقة تشوف اللينك (10 دقايق)

### 1. GitHub — ارفع المشروع
1. اعمل حساب مجاني على [github.com](https://github.com) لو معندكش
2. اضغط **+** فوق يمين → **New repository**
3. الاسم: `noon-tracker` | خليه **Public** | Create
4. في الصفحة الجديدة اضغط **uploading an existing file** واسحب كل ملفات المشروع

### 2. شغل الـ Scraper (Actions)
- روح تبويب **Actions** → اضغط **I understand my workflows, go ahead and enable them**
- اضغط **Daily Noon Egypt Scraper** → **Run workflow** → **Run workflow** (الزرار الأخضر)
- استنى 3-5 دقايق. لو نجح، هتلاقي ملف `noon_data.db` ظهر في الـ repo ✅

**لو ظهر أحمر (Cloudflare block):**
- سجل ببلاش على [scraperapi.com](https://scraperapi.com) → انسخ الـ API key
- في الـ repo: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
- Name: `SCRAPERAPI_KEY` | Value: الـ key
- ارجع Actions وشغل الـ workflow تاني

### 3. Streamlit Cloud — اطلع اللينك
1. روح [share.streamlit.io](https://share.streamlit.io) → **Sign in with GitHub**
2. اضغط **New app**
3. اختار: Repository = `noon-tracker`, Branch = `main`, Main file = `dashboard.py`
4. **Deploy**
5. بعد دقيقتين → **اللينك جاهز** 🎉  
   شكله: `https://<username>-noon-tracker.streamlit.app`

افتحه من الموبايل، احفظه على الـ home screen.

---

## 📊 اللي هتلاقيه في الـ Dashboard

- **🏆 Sales Leaderboard** — كل المنتجات مرتبة حسب 🔥 المبيعات (الرقم الأساسي)
- **📈 Biggest Movers** — اللي مبيعاتهم قفزت أو نزلت من امبارح لليوم
- **🆕 New Best Sellers** — منتجات جديدة دخلت الترتيب أو أخدت شارة Best Seller
- **💰 Price Changes** — تغيرات الأسعار (بس للمنتجات اللي فعلاً بتبيع)
- **🔍 Search** — دور على أي منتج + شوف رسم بياني للمبيعات والأسعار
- **📊 Raw Data** — الداتا كاملة + تحميل CSV

**Filter مهم:** في الجنب slider اسمه "Min. units sold" — حطه على 100 أو 200 عشان يخفي المنتجات اللي مش بتبيع.

---

## 🔄 التشغيل التلقائي

الـ scraper بيشتغل تلقائياً كل يوم 8 صباحاً بتوقيت القاهرة. الـ dashboard بيتحدث لوحده كل مرة الداتا تتحدث. مفيش حاجة عليك تعملها.

---

## ⚙️ التخصيص

- **تضيف/تشيل categories:** عدل `categories.py`
- **تغير وقت التشغيل:** عدل الـ cron في `.github/workflows/scrape.yml`
- **محلياً على جهازك:** `pip install -r requirements.txt` → `python scraper.py` → `streamlit run dashboard.py`

---

## ⚠️ ملاحظات

- أرقام "sold recently" اللي بيعرضها نون على شكل ranges (`210+`). النظام بياخد الحد الأدنى (210). المهم هو الترند بمرور الوقت مش الرقم المطلق.
- استخدم الداتا لأغراض داخلية (market research بتاعتك). ماتنشرش الداتا الخام.
