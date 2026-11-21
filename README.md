# NHL-PLAYER-SIGNAL • DEG1 = 88 (28 GEMINI / AIR)

سیستم هوشمند پیش‌بینی بازیکن‌محور برای **۳۲ تیم هاکی NHL** (شامل **Utah Mammoth** در استادیوم `Delta Center`) بدون آینده‌نگری (`r.d < g.d`):

- **ثابت پایه NHL:** `DEG1 = 88` (`28 GEMINI` / عنصر `AIR`)
- **فرمول حالت C (پیش‌فرض):**
  - `DEG1 = 88`
  - `DEG2 = EnglishGem(Full_Name) mod 360`
  - `DEG3 = Jersey_No_Eff mod 360`
- **ترکیب و وزن حضور بازیکنان:** ۸ بازیکن فعال برتر هر تیم بر اساس **میانگین زمان روی یخ (TOI)** پیش از بازی با حذف خودکار مصدومان و محرومان (`OUT, IR, IR-LT, IR-NR, Suspension`) از وب‌سرویس رسمی `sports/hockey/nhl` در ESPN.
- **حفظ کامل موتور ریاضی و نجومی:** محاسبات نجومی زیر آسمان و مختصات استادیوم میزبان ۳۲ تیم NHL، شاخص‌های `ELE-P`، `ELE-FINAL`، `ELE-DYN`، قطبیت ۱۲ ستونی، مدل تلفیقی ۵ روش (`F30`)، و آرایه ۳ عددی ۴ کاناله (`idx3`).
- **امنیت شیت‌های زنده:** آیدی شیت‌های گوگل به متغیرهای محیطی `NHL_PLAYER_INPUT_SHEET_ID` و `NHL_PLAYER_CALC_SHEET_ID` منتقل شده و دارای پشتیبان JSON محلی (`artifacts/api-server/data/`) و محافظ مسدودسازی شیت‌های زنده NBA است.

## دستورات اصلی

```bash
pnpm install
pnpm run build

# دریافت لیست بازیکنان ۳۲ تیم NHL، وضعیت مصدومان، آمار TOI و ساخت دیتابیس NHL-PLAYERS-GEM:
python3 artifacts/api-server/python/fetch_nhl_players_2010_2027.py

# ساخت هر ۳ حالت DEG3 (Mode C / Mode B / Mode A) بدون آینده‌نگری (۲۰۱۰ تا ۲۰۲۷):
python3 artifacts/api-server/python/build_all_player_modes.py

# همگام‌سازی زنده نتایج ESPN هاکی و تست ترمینال روی یک بازی NHL:
python3 artifacts/api-server/python/nhl_live_sync.py --target-date 2026-11-18 --test-game --game-index 2
```
