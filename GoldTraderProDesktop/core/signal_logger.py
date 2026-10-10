"""ثبت سیگنال‌ها و خروجی Excel بدون داده آزمایشی."""
from pathlib import Path
from datetime import datetime, timezone
import csv,json
from openpyxl import Workbook
from openpyxl.styles import Font,PatternFill
class SignalLogger:
    def __init__(self,root=None):
        self.root=Path(root or Path(__file__).resolve().parents[1]); self.logs=self.root/"logs"; self.logs.mkdir(parents=True,exist_ok=True)
        self.json_path=self.logs/"detailed_signals.json"; self.csv_path=self.logs/"performance_full.csv"
    def all(self):
        try:return json.loads(self.json_path.read_text(encoding="utf-8"))
        except (OSError,ValueError):return []
    def append(self,signal):
        if signal.get("action") not in ("BUY","SELL","WAIT"):raise ValueError("Invalid signal action")
        rows=self.all(); row=dict(signal); row["id"]=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        rows.append(row); tmp=self.json_path.with_suffix(".tmp"); tmp.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(self.json_path)
        fields=sorted({k for r in rows for k in r if not isinstance(r.get(k),(dict,list))})
        with self.csv_path.open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows([{k:r.get(k,"") for k in fields} for r in rows])
        return row
    def export_excel(self,path=None):
        rows=self.all(); path=Path(path or self.logs/"signals_report.xlsx")
        wb=Workbook(); ws=wb.active; ws.title="سیگنال‌ها"
        fields=["id","issued_at","action","entry","sl","tp1","tp2","score","risk","status"]
        ws.append(fields)
        for row in rows:ws.append([row.get(k,"") for k in fields])
        for cell in ws[1]:
            cell.font=Font(bold=True,color="FFFFFF");cell.fill=PatternFill("solid",fgColor="243247")
        detail=wb.create_sheet("دلایل")
        detail.append(["شناسه","نوع","دلایل"])
        for row in rows:detail.append([row.get("id",""),row.get("action","")," | ".join(row.get("reasons",[])) if isinstance(row.get("reasons"),list) else row.get("reason","")])
        stats=wb.create_sheet("آمار")
        stats.append(["شاخص","مقدار"]);stats.append(["کل سیگنال‌ها",len(rows)]);stats.append(["خرید",sum(r.get("action")=="BUY" for r in rows)]);stats.append(["فروش",sum(r.get("action")=="SELL" for r in rows)]);stats.append(["انتظار",sum(r.get("action")=="WAIT" for r in rows)])
        for sh in wb.worksheets:
            sh.freeze_panes="A2";sh.auto_filter.ref=sh.dimensions
            for col in sh.columns:
                letter=col[0].column_letter;sh.column_dimensions[letter].width=min(52,max(14,max(len(str(c.value or "")) for c in col)+2))
        wb.save(path);return path
