import sys
from PyQt6 import QtWidgets
from ui.main_window import MainWindow
from ui.styles import APP_STYLE
def main():
    app=QtWidgets.QApplication(sys.argv);app.setApplicationName("GoldTrader Pro");app.setStyle("Fusion");app.setStyleSheet(APP_STYLE)
    window=MainWindow();window.show();sys.exit(app.exec())
if __name__=="__main__":main()
