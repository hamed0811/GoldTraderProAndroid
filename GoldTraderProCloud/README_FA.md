# GoldTrader Pro Cloud — Oracle + Cloudflare

این بسته بک‌اند ابری GoldTrader Pro است. از موتور تحلیل موجود در \`GoldTraderProDesktop/core\` استفاده می‌کند، داده را در SQLite/WAL نگه می‌دارد و فقط با quote/candle واقعی و زمان‌دار تحلیل می‌کند. **هیچ سفارش معاملاتی ارسال نمی‌شود و هیچ قیمت/سیگنال ساختگی تولید نمی‌شود.**

## محدودیت مهم معماری
- Oracle میزبانی API را انجام می‌دهد؛ Cloudflare Tunnel آدرس HTTPS را به API می‌رساند، بدون بازکردن پورت ورودی API در Oracle.
- این سرویس خودش قیمت XAUUSD تأمین نمی‌کند. پل ویندوزی/MT5 موجود در \`bridge\` باید داده واقعی بفرستد.
- در نتیجه تا وقتی ویندوز، MT5، حساب کارگزار و پل روشن باشند داده زنده می‌رسد. با خاموش‌شدن آنها، داده منقضی شده و API \`NO_DATA\` برمی‌گرداند.
- استقلال ۲۴/۷ از رایانه ویندوزی نیازمند دیتافید مجاز و سازگار با سرور است که جداگانه باید از نظر هزینه، تازه‌بودن، سهمیه و تاریخچه تأیید شود. این بسته یک API ناشناخته را رایگان/قطعی فرض نمی‌کند.
- منابع Oracle Always Free به ظرفیت و شرایط حساب وابسته‌اند؛ دامنه سفارشی Cloudflare نیز ممکن است هزینه خرید/تمدید داشته باشد.

## نصب روی Oracle Ubuntu
۱. یک VM واجد شرایط Oracle Always Free با Ubuntu بساز و با SSH وارد آن شو. کلید خصوصی SSH را افشا نکن.
۲. روی رایانه ویندوزی، ZIP خروجی را استخراج کن و کل ساختار آن را مثلاً در \`/opt/goldtraderpro-deploy\` کپی کن. باید این دو مسیر کنار هم باشند:

\`\`\`text
/opt/goldtraderpro-deploy/
  GoldTraderProCloud/
  GoldTraderProDesktop/core/
\`\`\`

۳. از SSH اجرا کن:

\`\`\`bash
cd /opt/goldtraderpro-deploy/GoldTraderProCloud/scripts
chmod +x install_oracle_ubuntu.sh
./install_oracle_ubuntu.sh
\`\`\`

اسکریپت Docker را در صورت نیاز نصب می‌کند، توکن‌های تصادفی جداگانه را در فایل خصوصی \`.env\` می‌سازد، API را بالا می‌آورد و \`/health\` را از داخل کانتینر امتحان می‌کند. فایل واقعی \`.env\` هرگز داخل ZIP یا GitHub قرار نمی‌گیرد.

## اتصال Cloudflare
۱. برای hostname پایدار، دامنه تحت کنترل خودت را در Cloudflare فعال کن.
۲. در Cloudflare Zero Trust → **Networks → Tunnels** یک Cloudflared Tunnel بساز.
۳. یک Public Hostname مثل \`api.example.com\` بساز و Service را روی \`http://api:8000\` بگذار (نام داخلی سرویس Docker است).
۴. توکن تونل را فقط در SSH سرور وارد کن:

\`\`\`bash
nano /opt/goldtraderpro-deploy/GoldTraderProCloud/.env
\`\`\`

\`CLOUDFLARE_TUNNEL_TOKEN\` را پر کن، سپس:

\`\`\`bash
cd /opt/goldtraderpro-deploy/GoldTraderProCloud
sudo docker compose --profile cloudflare up -d cloudflared
sudo docker compose ps
sudo docker compose logs --tail=80 cloudflared
\`\`\`

سرویس API هیچ پورت عمومی منتشر نمی‌کند. رمزهای ingest و read جدا هستند. Rate limiting و سیاست‌های دسترسی را در Cloudflare هم تنظیم کن.

## راه‌اندازی پل Windows/MT5
۱. MT5 را روی رایانه ویندوزی باز کن و به حساب کارگزار متصل شو.
۲. پوشه \`GoldTraderProCloud/bridge\` را به ویندوز کپی و \`start_mt5_bridge.bat\` را اجرا کن.
۳. بار اول Notepad با \`.env\` باز می‌شود. در آن:
- \`GOLDTRADER_API_URL=https://api.example.com\` را با hostname واقعی عوض کن.
- \`GOLDTRADER_INGEST_TOKEN\` را از فایل خصوصی Oracle بگیر.
- \`MT5_SYMBOL\` را برابر نام دقیق طلا در Market Watch بگذار، مانند \`XAUUSD.a\`.
۴. ذخیره کن و کنسول را ادامه بده. پل فقط Tick و کندل بسته‌شده ارسال می‌کند و تابع سفارش‌گذاری ندارد. کنسول و MT5 باید روشن بمانند.

رمزها را در کد، GitHub یا این گفتگو قرار نده.

## API
- \`GET /health\` — فقط زنده‌بودن فرایند؛ اتصال بازار را تأیید نمی‌کند.
- \`GET /ready\` — وضعیت دیتابیس و quote پیش‌فرض XAUUSD.
- \`POST /v1/market/tick\` — با \`Authorization: Bearer <GOLDTRADER_INGEST_TOKEN>\`.
- \`POST /v1/market/candles\` — با همان ingest token.
- \`GET /v1/market/latest?symbol=XAUUSD.a\` — با \`GOLDTRADER_READ_TOKEN\`.
- \`GET /v1/status?symbol=XAUUSD.a\` — وضعیت quote و کندل‌ها.
- \`GET /v1/signal/latest?symbol=XAUUSD.a\` — موتور تحلیل و فیلتر M15/H4/D1؛ حداقل نسبت پاداش/ریسک 1.5 روی TP2.

Quote باید حداکثر ۱۵ ثانیه عمر داشته باشد. برای سیگنال، تاریخچه تازه و کافی لازم است (M5≥60، M15≥30، H1≥30، H4≥202، D1≥52 کندل). در غیر این صورت \`NO_DATA\`/ \`WAIT\` برمی‌گردد. \`/health\` با \`status=ok\` یعنی فقط پروسه پاسخ می‌دهد.

تست امن از PowerShell محلی (Read token را وارد کن، نه در چت):

\`\`\`powershell
$env:GOLDTRADER_READ_TOKEN = Read-Host 'Read token from private Oracle .env'
Invoke-RestMethod -Headers @{ Authorization = "Bearer $env:GOLDTRADER_READ_TOKEN" } -Uri 'https://api.example.com/v1/status?symbol=XAUUSD.a'
\`\`\`

## نگهداری
\`\`\`bash
cd /opt/goldtraderpro-deploy/GoldTraderProCloud
sudo docker compose ps
sudo docker compose logs --tail=100 api
sudo docker compose restart api
\`\`\`

قبل از ارتقا از \`data/goldtrader.sqlite3\` نسخه پشتیبان بگیر. پوشه \`.env\` و \`data/\` را پاک نکن.

## محدودیت‌های شناخته‌شده
- UI دسکتاپ فعلی هنوز به API جدید سوییچ نشده؛ این بسته API و پل داده را فراهم می‌کند. یکپارچه‌سازی رابط کاربری، مرحله جداگانه‌ای است.
- تقویم اقتصادی قابل‌اعتماد/برنامه‌ریزی‌شده در این سرویس تنظیم نشده؛ خاموشی ۳۰ دقیقه قبل از رویداد را تضمین نمی‌کند.
- tick-volume فقط مقدار اعلامی کارگزار است، نه حجم جهانی یا ردیابی واقعی کیف‌پول نهنگ‌ها.
- \`NO_DATA\` در نبود خوراک تازه عمداً ایمن‌تر از سیگنال جعلی است.
