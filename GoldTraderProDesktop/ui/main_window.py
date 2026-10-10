"""رابط فارسی GoldTrader Pro؛ فقط تحلیل و سیگنال، بدون اجرای سفارش."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
import pandas as pd
import pyqtgraph as pg
from PyQt6 import QtCore,QtWidgets
from core.mt5_engine import MT5Engine
from core.indicators import ema,rsi,macd,bollinger,stochastic
from core.analyzer import analyze_market
from core.signal_engine import build_signal
from core.signal_logger import SignalLogger
from core.news_engine import fetch_news
from core.risk_manager import RiskManager
from core.alarm import alert
from ui.styles import APP_STYLE
from ui.widgets.candle_chart import CandleChart

ROOT=Path(__file__).resolve().parents[1]
TIMEFRAMES={"۱ دقیقه":"M1","۲ دقیقه":"M2","۳ دقیقه":"M3","۵ دقیقه":"M5","۱۵ دقیقه":"M15","۳۰ دقیقه":"M30","۱ ساعت":"H1","۴ ساعت":"H4","روزانه":"D1"}
CANDLE_COUNTS={"M1":120,"M2":150,"M3":150,"M5":200,"M15":300,"M30":300,"H1":400,"H4":500,"D1":365}
class NewsWorker(QtCore.QThread):
    finished_data=QtCore.pyqtSignal(object)
    def run(self):self.finished_data.emit(fetch_news())
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle("GoldTrader Pro | تحلیل و سیگنال طلا");self.resize(1480,920);self.setLayoutDirection(QtCore.Qt.LayoutDirection.RightToLeft);self.setStyleSheet(APP_STYLE)
        self.settings=json.loads((ROOT/"config"/"default.json").read_text(encoding="utf-8"));self.engine=MT5Engine(self.settings["mt5"]["symbol"]);self.logger=SignalLogger(ROOT);self.risk=RiskManager()
        self.tf="M5";self.last_signal=None;self.last_logged_key=None;self.df=pd.DataFrame();self.analysis={};self.tick_data=None;self.news_data={"status":"NO DATA","items":[]};self._build_ui()
        self.timer=QtCore.QTimer(self);self.timer.timeout.connect(self.refresh_market);self.timer.start(2500);self.refresh_market();self.refresh_history_table()
    def _build_ui(self):
        root=QtWidgets.QWidget();layout=QtWidgets.QVBoxLayout(root);layout.setContentsMargins(14,12,14,12);layout.setSpacing(10)
        header=QtWidgets.QHBoxLayout();title=QtWidgets.QLabel("GOLDTRADER PRO");title.setObjectName("Title");self.connection=QtWidgets.QLabel("● قطع از MT5");self.connection.setObjectName("Muted")
        self.price=QtWidgets.QLabel("NO DATA");self.price.setObjectName("Price");self.spread=QtWidgets.QLabel("اسپرد: —");self.clock=QtWidgets.QLabel("آخرین به‌روزرسانی: —")
        header.addWidget(title);header.addStretch();header.addWidget(self.connection);header.addSpacing(20);header.addWidget(self.price);header.addWidget(self.spread);layout.addLayout(header)
        self.tabs=QtWidgets.QTabWidget();layout.addWidget(self.tabs,1)
        self.monitor=QtWidgets.QWidget();m=QtWidgets.QVBoxLayout(self.monitor);toolbar=QtWidgets.QHBoxLayout()
        self.tfbox=QtWidgets.QComboBox()
        for label,value in TIMEFRAMES.items():self.tfbox.addItem(label,value)
        self.tfbox.setCurrentIndex(3);self.tfbox.currentIndexChanged.connect(self.change_timeframe)
        self.refresh_btn=QtWidgets.QPushButton("به‌روزرسانی");self.refresh_btn.clicked.connect(self.refresh_market)
        self.back_live=QtWidgets.QPushButton("بازگشت به زنده");self.back_live.clicked.connect(lambda:self.chart.enableAutoRange())
        self.news_btn=QtWidgets.QPushButton("به‌روزرسانی اخبار");self.news_btn.clicked.connect(self.load_news)
        for w in (QtWidgets.QLabel("تایم‌فریم:"),self.tfbox,self.refresh_btn,self.back_live,self.news_btn):toolbar.addWidget(w)
        toolbar.addStretch();toolbar.addWidget(self.clock);m.addLayout(toolbar)
        cards=QtWidgets.QHBoxLayout();self.signal_card=self._card("آخرین تصمیم","انتظار / WAIT");self.indicator_card=self._card("وضعیت تحلیل","در انتظار داده واقعی");self.market_card=self._card("بازار","XAUUSD")
        cards.addWidget(self.signal_card);cards.addWidget(self.indicator_card);cards.addWidget(self.market_card);m.addLayout(cards)
        self.chart=CandleChart();self.chart.crosshair_data.connect(self.statusBar().showMessage);m.addWidget(self.chart,5)
        self.rsi_plot=pg.PlotWidget(background='#0d1117');self.rsi_plot.setMaximumHeight(105);self.rsi_plot.setTitle('RSI (14)');self.rsi_plot.showGrid(x=True,y=True,alpha=0.15);self.rsi_plot.setYRange(0,100);m.addWidget(self.rsi_plot)
        self.macd_plot=pg.PlotWidget(background='#0d1117');self.macd_plot.setMaximumHeight(115);self.macd_plot.setTitle('MACD (12,26,9)');self.macd_plot.showGrid(x=True,y=True,alpha=0.15);m.addWidget(self.macd_plot)
        self.stoch_plot=pg.PlotWidget(background='#0d1117');self.stoch_plot.setMaximumHeight(90);self.stoch_plot.setTitle('Stochastic (14,3,3)');self.stoch_plot.setYRange(0,100);self.stoch_plot.showGrid(x=True,y=True,alpha=0.15);m.addWidget(self.stoch_plot)
        lower=QtWidgets.QHBoxLayout();self.reasons=QtWidgets.QListWidget();self.reasons.setMaximumHeight(150);lower.addWidget(self._panel("دلایل تصمیم",self.reasons),3)
        self.pending=QtWidgets.QTableWidget(0,8);self.pending.setHorizontalHeaderLabels(["نوع","سطح","فاصله $","اطمینان","SL","TP1","TP2","منابع"]);self.pending.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch);lower.addWidget(self._panel("سیگنال‌های پیش‌بینی",self.pending),2);m.addLayout(lower)
        self.tabs.addTab(self.monitor,"📊 مانیتور زنده")
        self.history_tab=QtWidgets.QWidget();hl=QtWidgets.QVBoxLayout(self.history_tab);stats=QtWidgets.QHBoxLayout()
        self.history_stats=QtWidgets.QLabel("نتیجه بر اساس لمس قیمت به سطوح سیگنال پایش می‌شود؛ این سود/زیان معامله واقعی نیست.")
        self.export_btn=QtWidgets.QPushButton("خروجی Excel");self.export_btn.clicked.connect(self.export_excel);self.history_refresh=QtWidgets.QPushButton("به‌روزرسانی");self.history_refresh.clicked.connect(self.refresh_history_table)
        stats.addWidget(self.history_stats);stats.addStretch();stats.addWidget(self.history_refresh);stats.addWidget(self.export_btn);hl.addLayout(stats)
        self.history=QtWidgets.QTableWidget(0,8);self.history.setHorizontalHeaderLabels(["شناسه","زمان","نوع","ورود","امتیاز","حد ضرر","هدف ۱","وضعیت"]);self.history.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch);self.history.setAlternatingRowColors(True);hl.addWidget(self.history);self.tabs.addTab(self.history_tab,"📜 سابقه سیگنال‌ها")
        self.news_tab=QtWidgets.QWidget();nl=QtWidgets.QVBoxLayout(self.news_tab);self.news_status=QtWidgets.QLabel("اخبار: هنوز دریافت نشده است");nl.addWidget(self.news_status);self.news_list=QtWidgets.QTableWidget(0,4);self.news_list.setHorizontalHeaderLabels(["جهت","عنوان","منبع","زمان"]);self.news_list.horizontalHeader().setSectionResizeMode(1,QtWidgets.QHeaderView.ResizeMode.Stretch);self.news_list.horizontalHeader().setSectionResizeMode(2,QtWidgets.QHeaderView.ResizeMode.Stretch);nl.addWidget(self.news_list);self.tabs.addTab(self.news_tab,"📰 اخبار بازار")
        self.settings_tab=QtWidgets.QWidget();sl=QtWidgets.QVBoxLayout(self.settings_tab);sl.addWidget(QtWidgets.QLabel("تنظیمات محلی — config/default.json"));self.settings_view=QtWidgets.QPlainTextEdit();self.settings_view.setReadOnly(True);self.settings_view.setPlainText(json.dumps(self.settings,ensure_ascii=False,indent=2));sl.addWidget(self.settings_view);sl.addWidget(QtWidgets.QLabel("این برنامه سیگنال و تحلیل ارائه می‌دهد؛ هیچ سفارش خرید یا فروشی ارسال نمی‌کند. داده‌ها فقط از اتصال واقعی MT5 دریافت می‌شوند."));self.tabs.addTab(self.settings_tab,"⚙️ تنظیمات")
        self.setCentralWidget(root);self.statusBar().showMessage("آماده — اتصال به MT5 لازم است")
    def _card(self,title,value):
        frame=QtWidgets.QFrame();frame.setObjectName("Card");v=QtWidgets.QVBoxLayout(frame);a=QtWidgets.QLabel(title);a.setObjectName("Muted");b=QtWidgets.QLabel(value);b.setWordWrap(True);b.setMinimumHeight(42);v.addWidget(a);v.addWidget(b);frame.value_label=b;return frame
    def _panel(self,title,widget):
        f=QtWidgets.QFrame();f.setObjectName("Card");v=QtWidgets.QVBoxLayout(f);v.addWidget(QtWidgets.QLabel(title));v.addWidget(widget);return f
    def change_timeframe(self):
        self.tf=self.tfbox.currentData();self.refresh_market()
    def refresh_market(self):
        try:
            tick=self.engine.tick()
            if not tick:
                self.connection.setText("● قطع از MT5");self.price.setText("NO DATA");self.statusBar().showMessage(self.engine.last_error or "داده واقعی دریافت نشد");return
            self.tick_data=tick
            if self.logger.track_price(tick['bid']):self.refresh_history_table()
            self.connection.setText("● متصل به MT5");self.price.setText(f"Bid {tick['bid']:.2f}  |  Ask {tick['ask']:.2f}");self.spread.setText(f"اسپرد: {tick['spread']:.2f}")
            self.df=self.engine.candles(self.tf,CANDLE_COUNTS.get(self.tf,300))
            if self.df.empty:self.statusBar().showMessage(self.engine.last_error or "کندل موجود نیست");return
            df15=self.df if self.tf=="M15" else self.engine.candles("M15",250)
            df1h=self.engine.candles("H1",250);df4h=self.engine.candles("H4",200);dfd1=self.engine.candles("D1",250)
            self.analysis=analyze_market(self.df,df15,df1h,df4h,dfd1,price=tick['bid'])
            self.last_signal=build_signal(self.analysis,tick,self.settings)
            key=(self.last_signal.get("action"),round(self.last_signal.get("entry",0),2),self.last_signal["issued_at"][:15])
            if key!=self.last_logged_key:
                self.logger.append(self.last_signal);self.last_logged_key=key;self.refresh_history_table()
                if self.last_signal.get('action') in ('BUY','SELL'):alert(self.last_signal['action'],self.settings.get('ui',{}).get('sound_alerts',True))
            close=self.df.close.astype(float).to_numpy();upper,mid,lower=bollinger(close);ema_lines={p:ema(close,p) for p in (9,21,50,200)};ema_lines['BB верх']=upper;ema_lines['BB низ']=lower
            self.chart.set_market_data(self.df,ema_lines,self.last_signal,self.analysis.get('levels'))
            rv=rsi(close,14);self.rsi_plot.clear();self.rsi_plot.plot(list(range(len(rv))),rv,pen=pg.mkPen('#a371f7',width=1.4));self.rsi_plot.addLine(y=70,pen=pg.mkPen('#f85149',style=QtCore.Qt.PenStyle.DashLine));self.rsi_plot.addLine(y=30,pen=pg.mkPen('#3fb950',style=QtCore.Qt.PenStyle.DashLine))
            ml,ms,mh=macd(close);self.macd_plot.clear();self.macd_plot.plot(list(range(len(ml))),ml,pen=pg.mkPen('#58a6ff',width=1.2));self.macd_plot.plot(list(range(len(ms))),ms,pen=pg.mkPen('#e3b341',width=1.2));self.macd_plot.addItem(pg.BarGraphItem(x=list(range(len(mh))),height=[0 if v!=v else float(v) for v in mh],width=0.6,brush='#30363d'))
            sk,sd=stochastic(self.df.high.astype(float).to_numpy(),self.df.low.astype(float).to_numpy(),close);self.stoch_plot.clear();self.stoch_plot.plot(list(range(len(sk))),sk,pen=pg.mkPen('#a371f7',width=1.2));self.stoch_plot.plot(list(range(len(sd))),sd,pen=pg.mkPen('#58a6ff',width=1.2));self.stoch_plot.addLine(y=80,pen=pg.mkPen('#f85149',style=QtCore.Qt.PenStyle.DashLine));self.stoch_plot.addLine(y=20,pen=pg.mkPen('#3fb950',style=QtCore.Qt.PenStyle.DashLine))
            self.signal_card.value_label.setText(self._signal_text(self.last_signal))
            self.indicator_card.value_label.setText(f"امتیاز: {self.analysis.get('score','—')} | RSI: {self.analysis.get('rsi') if self.analysis.get('rsi') is not None else '—'} | ADX: {self.analysis.get('adx') if self.analysis.get('adx') is not None else '—'}")
            self.market_card.value_label.setText(f"نماد: {self.settings['mt5']['symbol']}\nتایم‌فریم: {self.tf} | کندل: {len(self.df)}")
            self.reasons.clear()
            for reason in self.last_signal.get("reasons",[]) if isinstance(self.last_signal.get("reasons",[]),list) else [self.last_signal.get("reason","")]:
                if reason:self.reasons.addItem(str(reason))
            self.pending.setRowCount(0)
            for row,item in enumerate(self.last_signal.get("pending",[])):
                self.pending.insertRow(row)
                vals=[item["action"],f"{item['level_price']:.2f}",f"{item['distance']:.2f}",f"{item['confidence']}%",f"{item['sl']:.2f}",f"{item['tp1']:.2f}",f"{item['tp2']:.2f}",", ".join(item.get("sources",[]))]
                for col,val in enumerate(vals):self.pending.setItem(row,col,QtWidgets.QTableWidgetItem(str(val)))
            self.clock.setText("آخرین به‌روزرسانی: "+datetime.now().strftime("%H:%M:%S"));self.statusBar().showMessage("داده واقعی دریافت شد؛ سیگنال‌ها فقط تحلیلی هستند.")
        except Exception as exc:self.statusBar().showMessage(f"خطا در به‌روزرسانی: {exc}")
    def _signal_text(self,s):
        action=s.get("action","WAIT");fa={"BUY":"خرید ▲","SELL":"فروش ▼","WAIT":"انتظار ⏳"}.get(action,"انتظار ⏳")
        if action in ("BUY","SELL"):return f"{fa} | امتیاز {s.get('score',0)}%\nورود {s.get('entry',0):.2f} | SL {s.get('sl',0):.2f}\nTP1 {s.get('tp1',0):.2f} | TP2 {s.get('tp2',0):.2f}"
        return f"{fa} | امتیاز {s.get('score',0)}\n{s.get('reason','شرایط ورود کامل نیست.')}"
    def refresh_history_table(self):
        rows=self.logger.all();self.history.setRowCount(len(rows))
        for i,r in enumerate(reversed(rows)):
            vals=[r.get("id",""),r.get("issued_at",""),r.get("action",""),r.get("entry","—"),r.get("score","—"),r.get("sl","—"),r.get("tp1","—"),r.get("result") or r.get("status","تحلیلی")]
            for j,val in enumerate(vals):self.history.setItem(i,j,QtWidgets.QTableWidgetItem(str(val)))
        self.history_stats.setText(f"کل ثبت‌ها: {len(rows)} | خرید: {sum(r.get('action')=='BUY' for r in rows)} | فروش: {sum(r.get('action')=='SELL' for r in rows)} | انتظار: {sum(r.get('action')=='WAIT' for r in rows)}")
    def export_excel(self):
        try:path=self.logger.export_excel();QtWidgets.QMessageBox.information(self,"خروجی آماده شد",f"فایل Excel ساخته شد:\n{path}")
        except Exception as exc:QtWidgets.QMessageBox.critical(self,"خطا",str(exc))
    def load_news(self):
        self.news_btn.setEnabled(False);self.news_status.setText("در حال بررسی RSS؛ در نبود دسترسی، NO DATA نمایش داده می‌شود.")
        self.worker=NewsWorker();self.worker.finished_data.connect(self.show_news);self.worker.start()
    def show_news(self,data):
        self.news_btn.setEnabled(True);self.news_data=data;self.news_status.setText(f"وضعیت: {data['status']} | خبر مرتبط: {len(data['items'])} | زمان: {data['checked_at']}")
        self.news_list.setRowCount(len(data["items"]))
        for i,item in enumerate(data["items"]):
            for j,val in enumerate([item["sentiment"],item["title"],item["source"],item["published"]]):self.news_list.setItem(i,j,QtWidgets.QTableWidgetItem(str(val)))
    def closeEvent(self,event):
        self.timer.stop();self.engine.shutdown();event.accept()
