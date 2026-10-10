import pyqtgraph as pg
from PyQt6 import QtCore, QtGui
class CandlestickItem(pg.GraphicsObject):
    def __init__(self,data=None):
        super().__init__();self.data=data or [];self.picture=QtGui.QPicture();self.generatePicture()
    def setData(self,data):
        self.data=data or [];self.generatePicture();self.prepareGeometryChange();self.update()
    def generatePicture(self):
        self.picture=QtGui.QPicture();p=QtGui.QPainter(self.picture)
        for x,o,c,l,h in self.data:
            color=QtGui.QColor("#3fb950" if c>=o else "#f85149")
            p.setPen(QtGui.QPen(color,1));p.drawLine(QtCore.QPointF(x,l),QtCore.QPointF(x,h))
            p.setBrush(QtGui.QBrush(color));p.drawRect(QtCore.QRectF(x-0.32,min(o,c),0.64,max(abs(c-o),0.01)))
        p.end()
    def paint(self,painter,option,widget):painter.drawPicture(0,0,self.picture)
    def boundingRect(self):return QtCore.QRectF(self.picture.boundingRect())
class CandleChart(pg.PlotWidget):
    def __init__(self,parent=None):
        super().__init__(parent=parent,background="#0d1117")
        self.showGrid(x=True,y=True,alpha=0.18);self.showAxis("right");self.hideAxis("left")
        self.getPlotItem().setLabel("right","قیمت");self.getPlotItem().setLabel("bottom","کندل")
        self.candles=CandlestickItem();self.addItem(self.candles);self.lines={}
        self.price_line=pg.InfiniteLine(angle=0,movable=False,pen=pg.mkPen("#ffd33d",width=1,style=QtCore.Qt.PenStyle.DashLine));self.addItem(self.price_line)
        self.signal_lines=[];self.level_lines=[];self.setMinimumHeight(350)
    def set_market_data(self,df,emas=None,signal=None,levels=None):
        if df is None or len(df)==0:return
        self.candles.setData([(i,float(r.open),float(r.close),float(r.low),float(r.high)) for i,r in enumerate(df.itertuples())])
        self.price_line.setValue(float(df.close.iloc[-1]))
        for line in self.lines.values():self.removeItem(line)
        self.lines={}
        for period,values in (emas or {}).items():
            valid=[(i,float(v)) for i,v in enumerate(values) if v==v]
            if valid:
                line=pg.PlotDataItem([p[0] for p in valid],[p[1] for p in valid],pen=pg.mkPen({"9":"#a371f7","21":"#58a6ff","50":"#e3b341","200":"#f85149"}.get(str(period),"#8b949e"),width=1.2))
                self.addItem(line);self.lines[period]=line
        for item in self.signal_lines:self.removeItem(item)
        self.signal_lines=[]
        for item in self.level_lines:self.removeItem(item)
        self.level_lines=[]
        if levels:
            for side,color in (("support","#3fb950"),("resistance","#f85149")):
                for level in levels.get(side,[]):
                    line=pg.InfiniteLine(angle=0,movable=False,pen=pg.mkPen(color,width=0.8,style=QtCore.Qt.PenStyle.DotLine));line.setValue(float(level["price"]));self.addItem(line);self.level_lines.append(line)
        if signal and signal.get("action") in ("BUY","SELL"):
            for key,color in (("entry","#58a6ff"),("sl","#f85149"),("tp1","#3fb950"),("tp2","#2ea043")):
                if signal.get(key) is not None:
                    line=pg.InfiniteLine(angle=0,movable=False,pen=pg.mkPen(color,width=1,style=QtCore.Qt.PenStyle.DashLine));line.setValue(float(signal[key]));self.addItem(line);self.signal_lines.append(line)
        self.setXRange(max(0,len(df)-130),len(df)+2,padding=0)
