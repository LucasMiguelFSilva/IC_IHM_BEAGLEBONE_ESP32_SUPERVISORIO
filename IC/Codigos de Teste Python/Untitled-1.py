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

MAX_PTS   = 60

class SerialManager:
    PATTERN = re.compile(
        r'\[S[aA]?[tT][aA]?[tT][uU][sS]\]\s*'
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
        try:
            self.ser = serial.Serial(port, int(baud), timeout=1)
            self.running = True
            threading.Thread(target=self._read_loop, daemon=True).start()
            self.on_log(f"CONECTADO: {port}", kind="info")
            return True
        except Exception as e:
            return str(e)

    def disconnect(self):
        self.running = False
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
                self.on_log("PORTA FECHADA", kind="info")
            except Exception:
                pass

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
                if self.ser and self.ser.in_waiting:
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
            except Exception:
                pass
            time.sleep(0.05)

class BigValueDisplay(tk.Frame):
    def __init__(self, parent, label, unit, color=ACC_GREEN, **kw):
        super().__init__(parent, bg=BG_CARD, padx=4, pady=2, **kw)
        tk.Label(self, text=label, bg=BG_CARD, fg=TXT_SEC,
                 font=("Helvetica", 7, "bold")).pack(anchor="w")
        self._val = tk.Label(self, text="---", bg=BG_CARD, fg=color,
                              font=("Courier New", 14, "bold"))
        self._val.pack(anchor="center")
        tk.Label(self, text=unit, bg=BG_CARD, fg=TXT_MUTE,
                 font=("Helvetica", 7)).pack(anchor="center")

    def set(self, val, fmt="{:.0f}"):
        try:
            self._val.config(text=fmt.format(val))
        except Exception:
            self._val.config(text=str(val))

class HomeFrame(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_ROOT)
        self.app = app
        self._build()

    def _build(self):
        wrapper = tk.Frame(self, bg=BG_ROOT)
        wrapper.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(wrapper, text="MOTOR SCADA", bg=BG_ROOT, fg=ACC_BLUE,
                 font=("Courier New", 16, "bold")).pack(pady=(0, 10))

        conn_card = tk.Frame(wrapper, bg=BG_PANEL, padx=10, pady=10)
        conn_card.pack(fill=tk.X)

        row1 = tk.Frame(conn_card, bg=BG_PANEL)
        row1.pack(fill=tk.X, pady=2)
        tk.Label(row1, text="PORTA:", bg=BG_PANEL, fg=TXT_SEC, font=("Helvetica", 8, "bold")).pack(side=tk.LEFT)
        
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_var = tk.StringVar(value=ports[0] if ports else "")
        self.port_cb = ttk.Combobox(row1, textvariable=self.port_var, values=ports, width=12, state="readonly")
        self.port_cb.pack(side=tk.LEFT, padx=4)
        
        tk.Button(row1, text="R", bg=BG_INPUT, fg=ACC_BLUE, font=("Helvetica", 8, "bold"),
                  command=self._refresh_ports).pack(side=tk.LEFT)

        row2 = tk.Frame(conn_card, bg=BG_PANEL)
        row2.pack(fill=tk.X, pady=4)
        tk.Label(row2, text="BAUD: ", bg=BG_PANEL, fg=TXT_SEC, font=("Helvetica", 8, "bold")).pack(side=tk.LEFT)
        self.baud_var = tk.StringVar(value="115200")
        ttk.Combobox(row2, textvariable=self.baud_var, values=["9600","19200","38400","57600","115200"],
                     width=8, state="readonly").pack(side=tk.LEFT, padx=4)

        self.conn_btn = tk.Button(conn_card, text="CONECTAR", bg=ACC_GREEN, fg=BG_DARK,
                                   font=("Helvetica", 9, "bold"), command=self._toggle)
        self.conn_btn.pack(fill=tk.X, pady=(6,0))

        self.status_lbl = tk.Label(conn_card, text="DESCONECTADO", bg=BG_PANEL, fg=TXT_MUTE, font=("Helvetica", 7, "bold"))
        self.status_lbl.pack(pady=(4, 0))

    def _refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cb["values"] = ports
        if ports: self.port_var.set(ports[0])

    def _toggle(self):
        if "CONECTAR" in self.conn_btn["text"]:
            res = self.app.serial_mgr.connect(self.port_var.get(), self.baud_var.get())
            if res is True:
                self.conn_btn.config(text="DESCONECTAR", bg=ACC_RED, fg="white")
                self.status_lbl.config(text=f"CONECTADO: {self.port_var.get()}", fg=ACC_GREEN)
                self.app.on_connect(self.port_var.get())
            else:
                messagebox.showerror("Erro", str(res), parent=self)
        else:
            self.app.serial_mgr.disconnect()
            self.conn_btn.config(text="CONECTAR", bg=ACC_GREEN, fg=BG_DARK)
            self.status_lbl.config(text="DESCONECTADO", fg=TXT_MUTE)
            self.app.on_disconnect()

class MonitorFrame(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self.app = app
        self._chart_started = False
        self._build()

    def _build(self):
        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        left = tk.Frame(body, bg=BG_DARK, width=130)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        top_values = tk.Frame(left, bg=BG_DARK)
        top_values.pack(fill=tk.X)
        self.display_real = BigValueDisplay(top_values, "RPM REAL", "rpm", color=ACC_GREEN)
        self.display_real.pack(fill=tk.X, pady=1)
        self.display_sp = BigValueDisplay(top_values, "SETPOINT", "rpm", color=ACC_BLUE)
        self.display_sp.pack(fill=tk.X, pady=1)

        status_col = tk.Frame(left, bg=BG_DARK)
        status_col.pack(fill=tk.BOTH, expand=True)

        self._status = {}
        for key, lbl, color, fmt in [("freq", "Hz", ACC_AMBER, "{:.1f}"), ("corr", "A", ACC_RED, "{:.1f}")]:
            card = tk.Frame(status_col, bg=BG_CARD, padx=4, pady=2)
            card.pack(fill=tk.X, pady=1)
            tk.Label(card, text=lbl, bg=BG_CARD, fg=TXT_SEC, font=("Helvetica", 7)).pack(side=tk.LEFT)
            v_lbl = tk.Label(card, text="-", bg=BG_CARD, fg=color, font=("Courier New", 10, "bold"))
            v_lbl.pack(side=tk.RIGHT)
            self._status[key] = (v_lbl, fmt)

        right = tk.Frame(body, bg=BG_CARD)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(2, 0))

        fig, self.ax = plt.subplots(figsize=(2.8, 1.8))
        fig.patch.set_facecolor(BG_CARD)
        self.ax.set_facecolor("#161b22")
        self.ax.tick_params(colors=TXT_SEC, labelsize=6)
        for sp in self.ax.spines.values(): sp.set_color(BORDER)
        self.ax.grid(True, color=BORDER, linewidth=0.5, alpha=0.6, linestyle="--")
        
        self.ln_real, = self.ax.plot([], [], color=ACC_GREEN, lw=1.5)
        self.ln_sp,   = self.ax.plot([], [], color=ACC_BLUE,  lw=1.0, ls="--")
        plt.tight_layout(pad=0.2)

        self.fig_canvas = FigureCanvasTkAgg(fig, master=right)
        self.fig_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

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
            self.ax.set_xlim(0, max(xs[-1], 20))
            all_v = list(hist["real"]) + list(hist["sp"])
            ymax = max(all_v) if all_v else 100
            self.ax.set_ylim(-10, ymax * 1.2 + 20)
            self.fig_canvas.draw_idle()
        self.after(800, self._tick_chart)

    def update_values(self, data):
        self.display_real.set(data.get("real", 0.0), "{:.0f}")
        self.display_sp.set(data.get("sp", 0.0), "{:.0f}")
        self._status["freq"][0].config(text=self._status["freq"][1].format(data.get("freq", 0.0)))
        self._status["corr"][0].config(text=self._status["corr"][1].format(data.get("corr", 0.0)))

class ControlFrame(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self.app = app
        self.mode_var = tk.StringVar(value="rpm") 
        self._build()
        self._update_status()

    def _build(self):
        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        left = tk.Frame(body, bg=BG_DARK, width=220)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        right = tk.Frame(body, bg=BG_DARK)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(2, 0))

        # --- SELETOR DE MODO ---
        mode_card = tk.Frame(left, bg=BG_PANEL, padx=4, pady=4)
        mode_card.pack(fill=tk.X, pady=(0, 2))
        tk.Label(mode_card, text="MODO DE OPERAÇÃO", bg=BG_PANEL, fg=TXT_SEC, font=("Helvetica", 7, "bold")).pack(anchor="w")
        
        rb_frame = tk.Frame(mode_card, bg=BG_PANEL)
        rb_frame.pack(fill=tk.X, pady=2)
        rb_rpm = tk.Radiobutton(rb_frame, text="Malha Fechada (RPM)", variable=self.mode_var, value="rpm",
                                bg=BG_PANEL, fg=TXT_PRI, selectcolor=BG_DARK, font=("Helvetica", 7), command=self._on_mode_change)
        rb_rpm.pack(anchor="w")
        rb_freq = tk.Radiobutton(rb_frame, text="Malha Aberta (Hz)", variable=self.mode_var, value="freq",
                                 bg=BG_PANEL, fg=TXT_PRI, selectcolor=BG_DARK, font=("Helvetica", 7), command=self._on_mode_change)
        rb_freq.pack(anchor="w")

        # --- CARD DE ENTRADA DE DADOS E SLIDER ---
        sp_card = tk.Frame(left, bg=BG_PANEL, padx=4, pady=4)
        sp_card.pack(fill=tk.X, pady=(0, 2))
        self.sp_label = tk.Label(sp_card, text="SETPOINT (RPM)", bg=BG_PANEL, fg=TXT_SEC, font=("Helvetica", 7, "bold"))
        self.sp_label.pack(anchor="w")
        
        row = tk.Frame(sp_card, bg=BG_PANEL)
        row.pack(fill=tk.X, pady=2)
        self.sp_entry = tk.Entry(row, font=("Courier New", 12, "bold"), bg=BG_INPUT, fg=ACC_GREEN, width=7, justify="center")
        self.sp_entry.pack(side=tk.LEFT)
        self.sp_entry.insert(0, "0.00")
        tk.Button(row, text="ENV", bg=ACC_BLUE, fg=BG_DARK, font=("Helvetica", 8, "bold"), command=self._send_sp).pack(side=tk.RIGHT)

        # Configuração do Slider compacto
        self.slider_var = tk.DoubleVar(value=0.0)
        self.slider = tk.Scale(sp_card, from_=0, to=2000, orient=tk.HORIZONTAL,
                               variable=self.slider_var, bg=BG_PANEL, fg=TXT_SEC,
                               troughcolor=BG_INPUT, activebackground=ACC_BLUE,
                               highlightthickness=0, bd=0, showvalue=0, sliderlength=15, width=12,
                               command=self._slider_moved)
        self.slider.pack(fill=tk.X, pady=(4, 0))

        # --- CARD DE COMANDOS ---
        cmd_card = tk.Frame(left, bg=BG_PANEL, padx=4, pady=4)
        cmd_card.pack(fill=tk.X, pady=2)
        tk.Button(cmd_card, text="RUN", bg=ACC_GREEN, fg=BG_DARK, font=("Helvetica", 8, "bold"), width=7, command=lambda: self._send_cmd("run")).pack(side=tk.LEFT, padx=1)
        tk.Button(cmd_card, text="STOP", bg=ACC_RED, fg="white", font=("Helvetica", 8, "bold"), width=7, command=lambda: self._send_cmd("stop")).pack(side=tk.LEFT, padx=1)
        tk.Button(cmd_card, text="RST", bg=ACC_AMBER, fg=BG_DARK, font=("Helvetica", 8, "bold"), width=5, command=lambda: self._send_cmd("reset")).pack(side=tk.LEFT, padx=1)

        # --- STATUS DA DIREITA ---
        self._status = {}
        for key, lbl, color, fmt in [("sp", "SP:", ACC_BLUE, "{:.0f}"), ("real", "RPM:", ACC_GREEN, "{:.0f}"), ("freq", "Hz:", ACC_AMBER, "{:.1f}")]:
            card = tk.Frame(right, bg=BG_CARD, padx=4, pady=2)
            card.pack(fill=tk.X, pady=1)
            tk.Label(card, text=lbl, bg=BG_CARD, fg=TXT_SEC, font=("Helvetica", 7)).pack(side=tk.LEFT)
            v_lbl = tk.Label(card, text="-", bg=BG_CARD, fg=color, font=("Courier New", 11, "bold"))
            v_lbl.pack(side=tk.RIGHT)
            self._status[key] = (v_lbl, fmt)

        self.log_txt = tk.Text(right, bg=BG_CARD, fg=ACC_GREEN, font=("Courier New", 7), state=tk.DISABLED, height=4)
        self.log_txt.pack(fill=tk.BOTH, expand=True, pady=(2,0))

    def _slider_moved(self, val):
        self.sp_entry.delete(0, tk.END)
        self.sp_entry.insert(0, f"{float(val):.2f}")

    def _on_mode_change(self):
        if self.mode_var.get() == "rpm":
            self.sp_label.config(text="SETPOINT (RPM)")
            self.slider.config(to=2000, resolution=1.0) 
        else:
            self.sp_label.config(text="FREQUÊNCIA (Hz)")
            self.slider.config(to=60, resolution=0.1) 
        
        self.sp_entry.delete(0, tk.END)
        self.sp_entry.insert(0, "0.00")
        self.slider_var.set(0)

    def append_log(self, text, kind="info"):
        self.log_txt.config(state=tk.NORMAL)
        self.log_txt.insert(tk.END, text + "\n")
        self.log_txt.see(tk.END)
        self.log_txt.config(state=tk.DISABLED)

    def _send_sp(self):
        try:
            val = float(self.sp_entry.get())
            if self.mode_var.get() == "rpm":
                self.app.serial_mgr.send(f"rpm:{val:.2f}")
            else:
                self.app.serial_mgr.send(f"freq:{val:.2f}")
            
            # Sincroniza o slider caso o usuario tenha digitado um valor manualmente
            self.slider_var.set(val) 
            
        except ValueError:
            self.append_log("ERR: Valor Invalido")

    def _send_cmd(self, cmd):
        self.app.serial_mgr.send(cmd)

    def _update_status(self):
        data = self.app.data
        for key, (lbl, fmt) in self._status.items():
            lbl.config(text=fmt.format(data.get(key, 0.0)))
        self.after(500, self._update_status)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SCADA")
        self.geometry("480x272")
        self.attributes("-fullscreen", True) # <- FORÇA TELA CHEIA (SEM BORDAS)
        self.bind("<Escape>", lambda e: self.destroy()) # Aperte ESC no teclado para sair
        self.configure(bg=BG_ROOT)

        self.data = {k: 0.0 for k in ("alvo", "sp", "real", "freq", "corr")}
        self.history = {k: deque(maxlen=MAX_PTS) for k in self.data}
        self.times = deque(maxlen=MAX_PTS)

        self.serial_mgr = SerialManager(on_data=self._on_data, on_log=self._on_log)

        self._build_navbar()
        self._build_frames()
        self.show_frame("monitor")
        self._sync_monitor()

    def _build_navbar(self):
        nb = tk.Frame(self, bg=BG_PANEL, height=30)
        nb.pack(fill=tk.X)
        nb.pack_propagate(False)

        tk.Frame(nb, bg=BORDER, height=1).place(relx=0, rely=1.0, anchor="sw", relwidth=1)

        for frame_id, label in [("home", "INICIO"), ("monitor", "MONITOR"), ("control", "CONTROLE")]:
            tk.Button(nb, text=label, bg=BG_PANEL, fg=TXT_PRI, relief=tk.FLAT, font=("Helvetica", 8, "bold"),
                      command=lambda n=frame_id: self.show_frame(n)).pack(side=tk.LEFT, padx=2)
            
        self.nav_conn = tk.Label(nb, text="OFF", bg=BG_PANEL, fg=TXT_MUTE, font=("Helvetica", 8, "bold"))
        self.nav_conn.pack(side=tk.RIGHT, padx=4)

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
        self.nav_conn.config(text="ON", fg=ACC_GREEN)
        if "control" in self.frames: self.frames["control"].append_log("CONECTADO")

    def on_disconnect(self):
        self.nav_conn.config(text="OFF", fg=TXT_MUTE)

    def _on_data(self, data):
        self.data.update(data)
        self.times.append(time.time())
        for k, v in data.items(): self.history[k].append(v)

    def _on_log(self, message, kind="info"):
        try:
            if "control" in self.frames: self.frames["control"].append_log(message)
        except: pass

    def _sync_monitor(self):
        self.frames["monitor"].update_values(self.data)
        self.after(500, self._sync_monitor)

if __name__ == "__main__":
    app = App()
    app.mainloop()