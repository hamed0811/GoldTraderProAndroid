import os
import sys
import threading
import webbrowser
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
        self.root.geometry("520x330")
        self.root.resizable(False, False)
        self.server = None

        tk.Label(root, text="GOLDTRADER PRO", font=("Segoe UI", 20, "bold")).pack(pady=(22, 4))
        tk.Label(root, text="Windows Signal Server", font=("Segoe UI", 11)).pack()

        self.status = tk.Label(root, text="● Starting...", font=("Segoe UI", 12))
        self.status.pack(pady=18)
        tk.Label(root, text=f"Local server: http://{HOST}:{PORT}", font=("Segoe UI", 10)).pack()

        frame = tk.Frame(root)
        frame.pack(pady=22)
        tk.Button(frame, text="Open Server", width=18, command=self.open_server).grid(row=0, column=0, padx=6)
        tk.Button(frame, text="Open Health", width=18, command=self.open_health).grid(row=0, column=1, padx=6)
        tk.Button(root, text="Exit Server", width=18, command=self.close).pack(pady=8)

        config = uvicorn.Config(backend_main.app, host=HOST, port=PORT, log_level="info", reload=False, access_log=True)
        self.server = uvicorn.Server(config)
        threading.Thread(target=self.server.run, daemon=True).start()

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(1000, self.refresh)

    def refresh(self):
        self.status.config(text="● Server RUNNING" if self.server.started else "● Starting server...")
        self.root.after(1000, self.refresh)

    def open_server(self):
        webbrowser.open(f"http://{HOST}:{PORT}")

    def open_health(self):
        webbrowser.open(f"http://{HOST}:{PORT}/health")

    def close(self):
        if self.server:
            self.server.should_exit = True
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    GoldTraderWindowsApp(root)
    root.mainloop()
