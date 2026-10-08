import json
import os
import sys
import threading
import urllib.request
import tkinter as tk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import uvicorn
import main as backend_main

HOST = "127.0.0.1"
PORT = 8000

class GoldTraderWindowsApp:
    def __init__(self, root):
        self.root = root
        self.root.title("GoldTrader Pro — Windows")
        self.root.geometry("620x470")
        self.root.resizable(False, False)
        self.server = None

        tk.Label(root, text="GOLDTRADER PRO", font=("Segoe UI", 22, "bold")).pack(pady=(18, 2))
        tk.Label(root, text="Windows Signal Terminal — SIGNAL ONLY", font=("Segoe UI", 10)).pack()
        self.status = tk.Label(root, text="● Starting...", font=("Segoe UI", 12))
        self.status.pack(pady=12)

        panel = tk.Frame(root, bd=1, relief="solid", padx=18, pady=14)
        panel.pack(fill="x", padx=24)
        self.price = self._row(panel, "Price")
        self.signal = self._row(panel, "Signal")
        self.entry = self._row(panel, "Entry")
        self.sl = self._row(panel, "Stop Loss")
        self.tp = self._row(panel, "Take Profit")
        self.conf = self._row(panel, "Confidence")
        self.reason = self._row(panel, "Reason")

        tk.Label(root, text=f"Server: http://{HOST}:{PORT}", font=("Segoe UI", 9)).pack(pady=12)
        tk.Button(root, text="Refresh", width=18, command=self.poll_state).pack(pady=4)
        tk.Button(root, text="Exit Server", width=18, command=self.close).pack(pady=4)

        config = uvicorn.Config(backend_main.app, host=HOST, port=PORT, log_level="info", reload=False, access_log=True)
        self.server = uvicorn.Server(config)
        threading.Thread(target=self.server.run, daemon=True).start()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(1000, self.refresh)

    def _row(self, parent, label):
        row = tk.Frame(parent)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label + ":", width=14, anchor="w", font=("Segoe UI", 10, "bold")).pack(side="left")
        value = tk.Label(row, text="NO DATA", anchor="w", font=("Segoe UI", 10))
        value.pack(side="left")
        return value

    def refresh(self):
        self.status.config(text="● Server RUNNING" if self.server.started else "● Starting server...")
        self.poll_state()
        self.root.after(2000, self.refresh)

    def poll_state(self):
        def worker():
            try:
                with urllib.request.urlopen(f"http://{HOST}:{PORT}/api/state", timeout=2) as response:
                    data = json.loads(response.read().decode("utf-8"))
                sig = data.get("signal") or {}
                self.root.after(0, lambda: self.apply_state(data, sig))
            except Exception:
                self.root.after(0, lambda: self.status.config(text="● Server / Data unavailable"))
        threading.Thread(target=worker, daemon=True).start()

    def apply_state(self, data, sig):
        self.price.config(text=data.get("price") or "NO DATA")
        self.signal.config(text=sig.get("state") or "WAIT")
        self.entry.config(text=str(sig.get("entry") or "—"))
        self.sl.config(text=str(sig.get("sl") or "—"))
        self.tp.config(text=str(sig.get("tp1") or "—"))
        confidence = sig.get("confidence")
        self.conf.config(text=f"{float(confidence):.0%}" if isinstance(confidence, (int, float)) else "—")
        self.reason.config(text=sig.get("reasons") or "No active signal")

    def close(self):
        if self.server:
            self.server.should_exit = True
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    GoldTraderWindowsApp(root)
    root.mainloop()
