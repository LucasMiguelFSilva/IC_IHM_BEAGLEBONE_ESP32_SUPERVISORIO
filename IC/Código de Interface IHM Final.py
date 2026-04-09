"""
MOTOR CONTROL SCADA — HMI COMPACTA (480x272)
Sistema Supervisório Industrial Otimizado
"""

import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import threading
import re
import time
from collections import deque

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ─── PALETA INDUSTRIAL (DARK MODE) ──────────────────────────────────────────
BG_ROOT   = "#080c10"
BG_DARK   = "#0d1117"
BG_PANEL  = "#161b22"
BG_CARD   = "#1c2128"
BG_INPUT  = "#21262d"

ACC_BLUE  = "#58a6ff"
ACC_GREEN = "#39d353"
ACC_RED   = "#f85149"
ACC_AMBER = "#e3b341"
ACC_CYAN  = "#79c0ff"

TXT_PRI   = "#e6edf3"
TXT_SEC   = "#8b949e"
TXT_MUTE  = "#484f58"
BORDER    = "#30363d"

MAX_PTS   = 80

# ─── GERENCIADOR SERIAL ─────────────────────────────────────────────────────
# ─── GERENCIADOR SERIAL ─────────────────────────────────────────────────────
class SerialManager:
    PATTERN = re.compile(
        r'\[.*?\]\s*'
        r'Alvo:\s*([\d.]+)\s*\|\s*SP:\s*([\d.]+)\s*\|\s*'
        r'Real:\s*([\d.]+)\s*\|\s*Out:\s*([\d.]+)\s*Hz\s*\|\s*I:\s*([\d.]+)\s*A'
    )

    def __init__(self, on_data, on_log):
        self.ser = None
        self.running = False
        self._lock = threading.Lock()
        self.on_data = on_data
        self.on_log = on_log

    def connect(self, port, baud=115200):
        # Desconecta de forma segura antes de tentar uma nova conexão
        if self.ser and self.ser.is_open:
            self.disconnect()
            
        try:
            self.ser = serial.Serial(port, int(baud), timeout=1)
            self.running = True
            threading.Thread(target=self._read_loop, daemon=True).start()
            self.on_log(f"CONECTADO: {port}", kind="info")
            return True
        except Exception as e:
            return str(e)

    def disconnect(self):
        # 1. Avisa a thread para parar
        self.running = False
        
        # 2. O SEGREDO PARA O LINUX: Esperar a thread de leitura sair do loop
        # antes de puxar a porta da tomada, evitando portas zumbis.
        time.sleep(0.15) 
        
        # 3. Fecha a porta de forma protegida
        with self._lock:
            if self.ser and self.ser.is_open:
                try:
                    self.ser.close()
                    self.on_log("PORTA FECHADA", kind="info")
                except Exception:
                    pass
            self.ser = None

    def send(self, msg: str):
        with self._lock:
            if self.ser and self.ser.is_open:
                try:
                    self.ser.write((msg.strip() + "\n").encode("utf-8"))
                    self.on_log(f"ENV: {msg}", kind="cmd")
                except Exception as e:
                    self.on_log(f"ERR: {e}", kind="error")
            else:
                self.on_log("OFFLINE", kind="warn")

    def _read_loop(self):
        buf = b""
        while self.running:
            try:
                if self.ser and self.ser.is_open and self.ser.in_waiting:
                    buf += self.ser.read(self.ser.in_waiting)
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        text = line.decode("utf-8", errors="ignore").strip()
                        if text:
                            m = self.PATTERN.search(text)
                            if m:
                                try:
                                    self.on_data({
                                        "alvo": float(m.group(1)),
                                        "sp":   float(m.group(2)),
                                        "real": float(m.group(3)),
                                        "freq": float(m.group(4)),
                                        "corr": float(m.group(5)),
                                    })
                                except Exception:
                                    pass
                            else:
                                self.on_log(text, kind="info")
            except Exception:
                pass
            time.sleep(0.02)


# ─── WIDGET: DISPLAY DIGITAL OTMIZADO ────────────────────────────────────────
class MiniDisplay(tk.Frame):
    def __init__(self, parent, label, unit, color=ACC_GREEN, font_size=16, **kw):
        super().__init__(parent, bg=BG_CARD, padx=6, pady=4, highlightbackground=BORDER, highlightthickness=1, **kw)
        header = tk.Frame(self, bg=BG_CARD)
        header.pack(fill=tk.X)
        tk.Label(header, text=label, bg=BG_CARD, fg=TXT_SEC, font=("Helvetica", 7, "bold")).pack(side=tk.LEFT)
        tk.Label(header, text=unit, bg=BG_CARD, fg=TXT_MUTE, font=("Helvetica", 7)).pack(side=tk.RIGHT)
        
        self._val = tk.Label(self, text="0.0", bg=BG_CARD, fg=color, font=("Courier New", font_size, "bold"))
        self._val.pack(anchor="center", pady=(2, 0))

    def set(self, val, fmt="{:.1f}"):
        try: self._val.config(text=fmt.format(val))
        except: self._val.config(text=str(val))


# ─── TELA: HOME / CONFIGURAÇÃO ───────────────────────────────────────────────
class HomeFrame(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_ROOT)
        self.app = app
        self._build()

    def _build(self):
        wrapper = tk.Frame(self, bg=BG_ROOT)
        wrapper.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(wrapper, text="⚙", bg=BG_ROOT, fg=ACC_BLUE, font=("Helvetica", 36)).pack(pady=(0, 0))
        tk.Label(wrapper, text="MOTOR SCADA HMI", bg=BG_ROOT, fg=TXT_PRI, font=("Courier New", 14, "bold")).pack(pady=(0, 15))

        conn_card = tk.Frame(wrapper, bg=BG_PANEL, padx=16, pady=12, highlightbackground=BORDER, highlightthickness=1)
        conn_card.pack(fill=tk.X)

        row1 = tk.Frame(conn_card, bg=BG_PANEL)
        row1.pack(fill=tk.X, pady=4)
        tk.Label(row1, text="PORTA:", bg=BG_PANEL, fg=TXT_SEC, font=("Helvetica", 8, "bold"), width=7, anchor="w").pack(side=tk.LEFT)
        
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_var = tk.StringVar(value=ports[0] if ports else "")
        self.port_cb = ttk.Combobox(row1, textvariable=self.port_var, values=ports, width=12, state="readonly")
        self.port_cb.pack(side=tk.LEFT, padx=4)
        
        tk.Button(row1, text="↻", bg=BG_INPUT, fg=ACC_BLUE, font=("Helvetica", 8), relief=tk.FLAT,
                  command=self._refresh_ports).pack(side=tk.LEFT)

        row2 = tk.Frame(conn_card, bg=BG_PANEL)
        row2.pack(fill=tk.X, pady=4)
        tk.Label(row2, text="BAUD: ", bg=BG_PANEL, fg=TXT_SEC, font=("Helvetica", 8, "bold"), width=7, anchor="w").pack(side=tk.LEFT)
        self.baud_var = tk.StringVar(value="115200")
        ttk.Combobox(row2, textvariable=self.baud_var, values=["9600","19200","38400","57600","115200"],
                     width=12, state="readonly").pack(side=tk.LEFT, padx=4)

        self.conn_btn = tk.Button(conn_card, text="CONECTAR", bg=ACC_GREEN, fg=BG_DARK, relief=tk.FLAT,
                                   font=("Helvetica", 9, "bold"), command=self._toggle)
        self.conn_btn.pack(fill=tk.X, pady=(10, 4))

        self.status_lbl = tk.Label(conn_card, text="○ DESCONECTADO", bg=BG_PANEL, fg=TXT_MUTE, font=("Helvetica", 7, "bold"))
        self.status_lbl.pack()

    def _refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cb["values"] = ports
        if ports: self.port_var.set(ports[0])

    def _toggle(self):
        if "CONECTAR" in self.conn_btn["text"]:
            res = self.app.serial_mgr.connect(self.port_var.get(), self.baud_var.get())
            if res is True:
                self.conn_btn.config(text="DESCONECTAR", bg=ACC_RED, fg="white")
                self.status_lbl.config(text=f"● CONECTADO ({self.port_var.get()})", fg=ACC_GREEN)
                self.app.on_connect(self.port_var.get())
            else:
                messagebox.showerror("Erro", str(res), parent=self)
        else:
            self.app.serial_mgr.disconnect()
            self.conn_btn.config(text="CONECTAR", bg=ACC_GREEN, fg=BG_DARK)
            self.status_lbl.config(text="○ DESCONECTADO", fg=TXT_MUTE)
            self.app.on_disconnect()


# ─── TELA: MONITORAMENTO ─────────────────────────────────────────────────────
class MonitorFrame(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self.app = app
        self._chart_started = False
        self._build()

    def _build(self):
        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        left = tk.Frame(body, bg=BG_DARK, width=140)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        self.d_real = MiniDisplay(left, "RPM REAL", "rpm", color=ACC_GREEN, font_size=20)
        self.d_real.pack(fill=tk.X, pady=(0, 4))
        
        self.d_sp = MiniDisplay(left, "SETPOINT", "rpm", color=ACC_BLUE, font_size=16)
        self.d_sp.pack(fill=tk.X, pady=4)

        row = tk.Frame(left, bg=BG_DARK)
        row.pack(fill=tk.X, pady=4)
        self.d_freq = MiniDisplay(row, "FREQ", "Hz", color=ACC_AMBER, font_size=12)
        self.d_freq.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        self.d_corr = MiniDisplay(row, "CORR", "A", color=ACC_RED, font_size=12)
        self.d_corr.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(2, 0))

        right = tk.Frame(body, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        fig, self.ax = plt.subplots(figsize=(3.0, 2.0))
        fig.patch.set_facecolor(BG_CARD)
        self.ax.set_facecolor(BG_PANEL)
        self.ax.tick_params(colors=TXT_SEC, labelsize=6)
        for sp in self.ax.spines.values(): sp.set_color(BORDER)
        self.ax.grid(True, color=BORDER, linewidth=0.5, alpha=0.6, linestyle="--")
        
        self.ln_real, = self.ax.plot([], [], color=ACC_GREEN, lw=1.8)
        self.ln_sp,   = self.ax.plot([], [], color=ACC_BLUE,  lw=1.0, ls="--")
        plt.tight_layout(pad=0.4)

        self.fig_canvas = FigureCanvasTkAgg(fig, master=right)
        self.fig_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

    def start_chart(self):
        if not self._chart_started:
            self._chart_started = True
            self._tick_chart()

    def _tick_chart(self):
        hist = self.app.history
        times = self.app.times
        if len(times) > 1:
            t0 = times[0]
            xs = [t - t0 for t in times]
            self.ln_real.set_data(xs, list(hist["real"]))
            self.ln_sp.set_data(xs, list(hist["sp"]))
            
            # ATUALIZADO: Focado em uma janela temporal de 20 segundos
            self.ax.set_xlim(max(0, xs[-1] - 20), max(xs[-1], 20))
            
            all_v = list(hist["real"]) + list(hist["sp"])
            ymax = max(all_v) if all_v else 100
            self.ax.set_ylim(-10, ymax * 1.2 + 20)
            self.fig_canvas.draw_idle()
        self.after(500, self._tick_chart)

    def update_values(self, data):
        self.d_real.set(data.get("real", 0.0), "{:.0f}")
        self.d_sp.set(data.get("sp", 0.0), "{:.0f}")
        self.d_freq.set(data.get("freq", 0.0), "{:.1f}")
        self.d_corr.set(data.get("corr", 0.0), "{:.1f}")


# ─── TELA: CONTROLE ──────────────────────────────────────────────────────────
class ControlFrame(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self.app = app
        self.mode_var = tk.StringVar(value="rpm") 
        self._build()

    def _build(self):
        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        left = tk.Frame(body, bg=BG_DARK, width=200)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        right = tk.Frame(body, bg=BG_DARK)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        # --- SELETOR DE MODO ---
        mode_card = tk.Frame(left, bg=BG_PANEL, padx=6, pady=4, highlightbackground=BORDER, highlightthickness=1)
        mode_card.pack(fill=tk.X, pady=(0, 6))
        
        tk.Radiobutton(mode_card, text="Controle Automatico (RPM)", variable=self.mode_var, value="rpm",
                       bg=BG_PANEL, fg=TXT_PRI, selectcolor=BG_DARK, font=("Helvetica", 7, "bold"), command=self._on_mode_change).pack(anchor="w")
        tk.Radiobutton(mode_card, text="Controle Manual (Hz)", variable=self.mode_var, value="freq",
                       bg=BG_PANEL, fg=TXT_PRI, selectcolor=BG_DARK, font=("Helvetica", 7, "bold"), command=self._on_mode_change).pack(anchor="w")

        # --- ENTRADA DE DADOS E TECLADO ---
        sp_card = tk.Frame(left, bg=BG_PANEL, padx=6, pady=4, highlightbackground=BORDER, highlightthickness=1)
        sp_card.pack(fill=tk.BOTH, expand=True)
        self.sp_label = tk.Label(sp_card, text="SETPOINT (RPM)", bg=BG_PANEL, fg=TXT_SEC, font=("Helvetica", 7, "bold"))
        self.sp_label.pack(anchor="w")
        
        row = tk.Frame(sp_card, bg=BG_PANEL)
        row.pack(fill=tk.X, pady=2)
        self.sp_entry = tk.Entry(row, font=("Courier New", 14, "bold"), bg=BG_INPUT, fg=ACC_GREEN, width=7, justify="center", relief=tk.FLAT)
        self.sp_entry.pack(side=tk.LEFT, ipady=3)
        self.sp_entry.insert(0, "0")
        
        tk.Button(row, text="▶ ENV", bg=ACC_BLUE, fg=BG_DARK, font=("Helvetica", 8, "bold"), relief=tk.FLAT, command=self._send_sp).pack(side=tk.RIGHT, fill=tk.Y)

        # Teclado Numérico IHM
        pad_frame = tk.Frame(sp_card, bg=BG_PANEL)
        pad_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        
        keys = [
            ('7', '8', '9'),
            ('4', '5', '6'),
            ('1', '2', '3'),
            ('C', '0', '.')
        ]
        
        for r, row_keys in enumerate(keys):
            pad_frame.rowconfigure(r, weight=1)
            for c, key in enumerate(row_keys):
                pad_frame.columnconfigure(c, weight=1)
                btn = tk.Button(pad_frame, text=key, bg=BG_INPUT, fg=TXT_PRI, font=("Helvetica", 10, "bold"), relief=tk.FLAT,
                                activebackground=BG_CARD, activeforeground=ACC_CYAN,
                                command=lambda k=key: self._pad_press(k))
                btn.grid(row=r, column=c, sticky="nsew", padx=1, pady=1, ipady=1)

        # --- COMANDOS DO MOTOR (AGORA NA DIREITA!) ---
        cmd_card = tk.Frame(right, bg=BG_PANEL, padx=6, pady=6, highlightbackground=BORDER, highlightthickness=1)
        cmd_card.pack(fill=tk.X, pady=(0, 6))
        
        tk.Label(cmd_card, text="COMANDOS", bg=BG_PANEL, fg=TXT_SEC, font=("Helvetica", 7, "bold")).pack(anchor="w", pady=(0,4))
        
        btn_row = tk.Frame(cmd_card, bg=BG_PANEL)
        btn_row.pack(fill=tk.X)
        
        # Botões ligeiramente mais altos (height=2) para facilitar o toque na tela
        tk.Button(btn_row, text="▶ RUN", bg=ACC_GREEN, fg=BG_DARK, font=("Helvetica", 10, "bold"), relief=tk.FLAT, height=2, command=lambda: self._send_cmd("run")).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        tk.Button(btn_row, text="■ STOP", bg=ACC_RED, fg="white", font=("Helvetica", 10, "bold"), relief=tk.FLAT, height=2, command=lambda: self._send_cmd("stop")).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        tk.Button(btn_row, text="↺ RST", bg=ACC_AMBER, fg=BG_DARK, font=("Helvetica", 10, "bold"), relief=tk.FLAT, height=2, command=lambda: self._send_cmd("reset")).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        # --- TERMINAL / LOG ---
        tk.Label(right, text="TERMINAL DE COMANDOS", bg=BG_DARK, fg=TXT_SEC, font=("Helvetica", 7, "bold")).pack(anchor="w")
        self.log_txt = tk.Text(right, bg=BG_CARD, fg=ACC_GREEN, font=("Courier New", 8), state=tk.DISABLED, highlightbackground=BORDER, highlightthickness=1)
        self.log_txt.pack(fill=tk.BOTH, expand=True, pady=(2,0))

    def _pad_press(self, key):
        current = self.sp_entry.get()
        
        # Limpar Tudo
        if key == 'C':
            self.sp_entry.delete(0, tk.END)
            self.sp_entry.insert(0, "0")
            return
            
        # Apaga o zero inicial para começar a digitar o valor
        if current == "0" and key != ".":
            current = ""
            
        self.sp_entry.delete(0, tk.END)
        self.sp_entry.insert(0, current + key)

    def _on_mode_change(self):
        if self.mode_var.get() == "rpm":
            self.sp_label.config(text="SETPOINT (RPM)")
        else:
            self.sp_label.config(text="FREQUÊNCIA (Hz)")
        
        self.sp_entry.delete(0, tk.END)
        self.sp_entry.insert(0, "0")

    def append_log(self, text, kind="info"):
        prefix = ">> " if kind == "cmd" else "-- "
        color = ACC_CYAN if kind == "cmd" else ACC_RED if kind == "error" else ACC_GREEN
        
        self.log_txt.config(state=tk.NORMAL)
        self.log_txt.insert(tk.END, prefix + text + "\n")
        self.log_txt.see(tk.END)
        self.log_txt.config(state=tk.DISABLED)

    def _send_sp(self):
        try:
            val = float(self.sp_entry.get())
            if self.mode_var.get() == "rpm":
                # Adicionado o prefixo 'rpm:' que o ESP32 está esperando
                self.app.serial_mgr.send(f"rpm:{val:.0f}")
            else:
                self.app.serial_mgr.send(f"freq:{val:.1f}")
        except ValueError:
            self.append_log("Valor Inválido", "error")

    def _send_cmd(self, cmd):
        self.app.serial_mgr.send(cmd)


# ─── APLICAÇÃO PRINCIPAL ─────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SCADA HMI")
        self.geometry("480x272")
        self.attributes("-fullscreen", True) # <- FORÇA TELA CHEIA PARA O DISPLAY
        self.bind("<Escape>", lambda e: self.destroy()) 
        self.configure(bg=BG_ROOT)

        self.data = {k: 0.0 for k in ("alvo", "sp", "real", "freq", "corr")}
        self.history = {k: deque(maxlen=MAX_PTS) for k in self.data}
        self.times = deque(maxlen=MAX_PTS)

        self.serial_mgr = SerialManager(on_data=self._on_data, on_log=self._on_log)

        self._build_navbar()
        self._build_frames()
        self.show_frame("home")
        self._sync_monitor()

    def _build_navbar(self):
        nb = tk.Frame(self, bg=BG_PANEL, height=32)
        nb.pack(fill=tk.X)
        nb.pack_propagate(False)

        tk.Frame(nb, bg=BORDER, height=1).place(relx=0, rely=1.0, anchor="sw", relwidth=1)

        for frame_id, icon, label in [("home", "⌂", "INÍCIO"), ("monitor", "📊", "MONITOR"), ("control", "🎛", "CONTROLE")]:
            btn = tk.Button(nb, text=f"{icon} {label}", bg=BG_PANEL, fg=TXT_PRI, relief=tk.FLAT, font=("Helvetica", 8, "bold"),
                            activebackground=BG_CARD, activeforeground=ACC_BLUE,
                            command=lambda n=frame_id: self.show_frame(n))
            btn.pack(side=tk.LEFT, padx=2, fill=tk.Y)
            
        self.nav_conn = tk.Label(nb, text="○ OFF", bg=BG_PANEL, fg=TXT_MUTE, font=("Helvetica", 8, "bold"))
        self.nav_conn.pack(side=tk.RIGHT, padx=8)

    def _build_frames(self):
        self.container = tk.Frame(self, bg=BG_DARK)
        self.container.pack(fill=tk.BOTH, expand=True)
        self.frames = {}
        for name, cls in [("home", HomeFrame), ("monitor", MonitorFrame), ("control", ControlFrame)]:
            f = cls(self.container, self)
            f.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.frames[name] = f

    def show_frame(self, name):
        self.frames[name].lift()
        if name == "monitor": self.frames["monitor"].start_chart()

    def on_connect(self, port):
        self.nav_conn.config(text="● ON", fg=ACC_GREEN)

    def on_disconnect(self):
        self.nav_conn.config(text="○ OFF", fg=TXT_MUTE)

    def _on_data(self, data):
        self.data.update(data)
        self.times.append(time.time())
        for k, v in data.items(): self.history[k].append(v)

    def _on_log(self, message, kind="info"):
        try:
            if "control" in self.frames: self.frames["control"].append_log(message, kind)
        except: pass

    def _sync_monitor(self):
        if hasattr(self.frames["monitor"], 'update_values'):
            self.frames["monitor"].update_values(self.data)
        self.after(500, self._sync_monitor)

if __name__ == "__main__":
    app = App()
    app.mainloop()