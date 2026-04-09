
"""
╔══════════════════════════════════════════════════════════════╗
║         MOTOR CONTROL SCADA — ESP32 + Inversor Modbus        ║
║         Sistema Supervisório Industrial — Python/Tkinter      ║
╚══════════════════════════════════════════════════════════════╝
Dependências:  pip install pyserial matplotlib
"""

import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import threading
import re
import time
import math
from collections import deque

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ─── PALETA INDUSTRIAL ────────────────────────────────────────────────────────
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
ACC_PURPLE= "#bc8cff"

TXT_PRI   = "#e6edf3"
TXT_SEC   = "#8b949e"
TXT_MUTE  = "#484f58"
BORDER    = "#30363d"

MAX_PTS   = 180  # 3 minutos a 1 Hz


# ─── GERENCIADOR SERIAL ───────────────────────────────────────────────────────
class SerialManager:
    """Thread de leitura/escrita serial não-bloqueante."""

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
            return True
        except Exception as e:
            return str(e)

    def disconnect(self):
        self.running = False
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass

    def send(self, msg: str):
        with self._lock:
            if self.ser and self.ser.is_open:
                try:
                    self.ser.write((msg.strip() + "\n").encode("utf-8"))
                except Exception as e:
                    self.on_log(f"[SERIAL ERR] {e}", color="red")

    def _read_loop(self):
        buf = b""
        while self.running:
            try:
                if self.ser.in_waiting:
                    buf += self.ser.read(self.ser.in_waiting)
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        text = line.decode("utf-8", errors="ignore").strip()
                        if text:
                            m = self.PATTERN.search(text)
                            if m:
                                self.on_data({
                                    "alvo": float(m.group(1)),
                                    "sp":   float(m.group(2)),
                                    "real": float(m.group(3)),
                                    "freq": float(m.group(4)),
                                    "corr": float(m.group(5)),
                                })
            except Exception:
                pass
            time.sleep(0.02)


# ─── WIDGET: GAUGE ANALÓGICO ──────────────────────────────────────────────────
class GaugeCanvas(tk.Canvas):
    """Gauge semicircular desenhado em Canvas."""

    def __init__(self, parent, label, unit, max_val, color=ACC_BLUE, size=170, **kw):
        super().__init__(parent, width=size, height=int(size * 0.78),
                         bg=BG_CARD, highlightthickness=0, **kw)
        self.s, self.label, self.unit = size, label, unit
        self.max_val, self.color = max_val, color
        self.value = 0.0
        self._draw(0)

    def set_value(self, val):
        v = max(0.0, min(float(val), self.max_val))
        if abs(v - self.value) > 0.05:
            self.value = v
            self._draw(v)

    def _arc_pts(self, cx, cy, r, a_start, sweep, steps=120):
        pts = []
        for i in range(steps + 1):
            a = math.radians(a_start + sweep * i / steps - 90)
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
        return pts

    def _draw(self, val):
        self.delete("all")
        s = self.s
        cx, cy = s / 2, s * 0.54
        R = s * 0.40
        pct = val / self.max_val if self.max_val else 0
        START, TOTAL = 215, 290

        # Track shadow
        pts = self._arc_pts(cx, cy, R, START, TOTAL)
        if len(pts) >= 4:
            self.create_line(*pts, fill="#1c2128", width=int(s * 0.09),
                             smooth=False, capstyle=tk.ROUND)

        # Track bg
        pts = self._arc_pts(cx, cy, R, START, TOTAL)
        if len(pts) >= 4:
            self.create_line(*pts, fill="#2d333b", width=int(s * 0.065),
                             smooth=False, capstyle=tk.ROUND)

        # Value arc
        if pct > 0.005:
            pts = self._arc_pts(cx, cy, R, START, TOTAL * pct)
            if len(pts) >= 4:
                self.create_line(*pts, fill=self.color, width=int(s * 0.065),
                                 smooth=False, capstyle=tk.ROUND)

        # Glow tip
        if pct > 0.02:
            tip_a = math.radians(START + TOTAL * pct - 90)
            tx = cx + R * math.cos(tip_a)
            ty = cy + R * math.sin(tip_a)
            gr = int(s * 0.06)
            self.create_oval(tx-gr, ty-gr, tx+gr, ty+gr,
                             fill=self.color, outline="", stipple="")

        # Center hub
        hub = int(s * 0.04)
        self.create_oval(cx-hub, cy-hub, cx+hub, cy+hub,
                         fill="#2d333b", outline=self.color, width=1)

        # Value text
        self.create_text(cx, cy - s * 0.08,
                         text=f"{val:.1f}",
                         fill=TXT_PRI, font=("Courier New", int(s * 0.14), "bold"),
                         anchor="center")

        # Unit
        self.create_text(cx, cy + s * 0.07,
                         text=self.unit,
                         fill=TXT_SEC, font=("Helvetica", int(s * 0.075)),
                         anchor="center")

        # Label
        self.create_text(cx, cy + s * 0.19,
                         text=self.label,
                         fill=self.color, font=("Helvetica", int(s * 0.079), "bold"),
                         anchor="center")

        # Min / Max
        def _endpoint(angle_deg, radius):
            a = math.radians(angle_deg - 90)
            return cx + radius * math.cos(a), cy + radius * math.sin(a)

        lx, ly = _endpoint(START, R * 1.22)
        rx, ry = _endpoint(START + TOTAL, R * 1.22)
        self.create_text(lx, ly, text="0", fill=TXT_MUTE,
                         font=("Helvetica", int(s * 0.065)))
        self.create_text(rx, ry, text=str(int(self.max_val)), fill=TXT_MUTE,
                         font=("Helvetica", int(s * 0.065)))


# ─── WIDGET: DISPLAY DIGITAL ──────────────────────────────────────────────────
class DigitDisplay(tk.Frame):
    def __init__(self, parent, label, unit, color=ACC_GREEN, wide=False, **kw):
        super().__init__(parent, bg=BG_CARD, padx=16 if wide else 12, pady=10, **kw)
        tk.Label(self, text=label, bg=BG_CARD, fg=TXT_SEC,
                 font=("Helvetica", 8, "bold")).pack()
        self._val = tk.Label(self, text="---", bg=BG_CARD, fg=color,
                              font=("Courier New", 20 if wide else 17, "bold"))
        self._val.pack()
        tk.Label(self, text=unit, bg=BG_CARD, fg=TXT_MUTE,
                 font=("Helvetica", 7)).pack()

    def set(self, val, fmt="{:.1f}"):
        self._val.config(text=fmt.format(val))


# ─── TELA: HOME ───────────────────────────────────────────────────────────────
class HomeFrame(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_ROOT)
        self.app = app
        self._build()

    def _build(self):
        # BG grid lines (decoração industrial)
        grid_cv = tk.Canvas(self, bg=BG_ROOT, highlightthickness=0)
        grid_cv.place(relx=0, rely=0, relwidth=1, relheight=1)
        for i in range(0, 2000, 60):
            grid_cv.create_line(i, 0, i, 2000, fill="#111820", width=1)
            grid_cv.create_line(0, i, 2000, i, fill="#111820", width=1)

        wrapper = tk.Frame(self, bg=BG_ROOT)
        wrapper.place(relx=0.5, rely=0.5, anchor="center")

        # ── Logo ──
        logo_row = tk.Frame(wrapper, bg=BG_ROOT)
        logo_row.pack()
        tk.Label(logo_row, text="⚙", bg=BG_ROOT, fg=ACC_BLUE,
                 font=("Helvetica", 52)).pack(side=tk.LEFT, padx=10)
        title_col = tk.Frame(logo_row, bg=BG_ROOT)
        title_col.pack(side=tk.LEFT)
        tk.Label(title_col, text="MOTOR CONTROL", bg=BG_ROOT, fg=TXT_PRI,
                 font=("Courier New", 32, "bold")).pack(anchor="w")
        tk.Label(title_col, text="SISTEMA SUPERVISÓRIO INDUSTRIAL",
                 bg=BG_ROOT, fg=ACC_BLUE,
                 font=("Helvetica", 11, "bold")).pack(anchor="w")

        # Separator
        tk.Frame(wrapper, bg=BORDER, height=1).pack(fill=tk.X, pady=22)

        # ── Conexão ──
        conn_card = tk.Frame(wrapper, bg=BG_PANEL, padx=28, pady=20)
        conn_card.pack(fill=tk.X)
        tk.Label(conn_card, text="▌ CONFIGURAÇÃO DE PORTA SERIAL",
                 bg=BG_PANEL, fg=ACC_CYAN, font=("Helvetica", 9, "bold")).pack(anchor="w", pady=(0,12))

        row = tk.Frame(conn_card, bg=BG_PANEL)
        row.pack(fill=tk.X)

        tk.Label(row, text="PORTA:", bg=BG_PANEL, fg=TXT_SEC,
                 font=("Helvetica", 9, "bold")).grid(row=0, column=0, padx=(0,6), sticky="e")

        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_var = tk.StringVar(value=ports[0] if ports else "")
        self.port_cb = ttk.Combobox(row, textvariable=self.port_var,
                                     values=ports, width=13, state="readonly",
                                     font=("Courier New", 10))
        self.port_cb.grid(row=0, column=1, padx=4)

        tk.Button(row, text="↺", bg=BG_INPUT, fg=ACC_BLUE, relief=tk.FLAT,
                  font=("Helvetica", 11, "bold"), cursor="hand2", padx=6,
                  command=self._refresh_ports).grid(row=0, column=2, padx=2)

        tk.Label(row, text="BAUD:", bg=BG_PANEL, fg=TXT_SEC,
                 font=("Helvetica", 9, "bold")).grid(row=0, column=3, padx=(18,6), sticky="e")

        self.baud_var = tk.StringVar(value="115200")
        ttk.Combobox(row, textvariable=self.baud_var, width=10,
                     values=["9600","19200","38400","57600","115200"],
                     state="readonly", font=("Courier New", 10)).grid(row=0, column=4, padx=4)

        self.conn_btn = tk.Button(row, text="  CONECTAR  ", bg=ACC_GREEN, fg=BG_DARK,
                                   relief=tk.FLAT, font=("Helvetica", 10, "bold"),
                                   padx=14, pady=7, cursor="hand2",
                                   command=self._toggle)
        self.conn_btn.grid(row=0, column=5, padx=(22, 0))

        # Status pill
        self.status_lbl = tk.Label(conn_card, text="○  DESCONECTADO",
                                    bg=BG_PANEL, fg=TXT_MUTE,
                                    font=("Helvetica", 9, "bold"))
        self.status_lbl.pack(anchor="w", pady=(10, 0))

        # ── Nav cards ──
        tk.Frame(wrapper, bg=BORDER, height=1).pack(fill=tk.X, pady=22)

        nav_row = tk.Frame(wrapper, bg=BG_ROOT)
        nav_row.pack()

        cards_cfg = [
            ("📊", "MONITORAMENTO", "Dados em tempo real\nGauges · Gráficos · Status", "monitor", ACC_BLUE),
            ("🎛", "CONTROLE", "Comandos ao motor\nRPM · Frequência · RUN/STOP", "control", ACC_AMBER),
        ]
        for icon, title, desc, frame, color in cards_cfg:
            self._nav_card(nav_row, icon, title, desc, frame, color)

    def _nav_card(self, parent, icon, title, desc, frame, color):
        card = tk.Frame(parent, bg=BG_PANEL, padx=36, pady=28, cursor="hand2")
        card.pack(side=tk.LEFT, padx=14)

        tk.Label(card, text=icon, bg=BG_PANEL, fg=color,
                 font=("Helvetica", 34)).pack()
        tk.Label(card, text=title, bg=BG_PANEL, fg=TXT_PRI,
                 font=("Helvetica", 13, "bold")).pack(pady=(6, 2))
        tk.Label(card, text=desc, bg=BG_PANEL, fg=TXT_SEC,
                 font=("Helvetica", 8), justify="center").pack()

        # Accent bottom border
        accent = tk.Frame(card, bg=color, height=2)
        accent.pack(fill=tk.X, pady=(14, 0))

        def go(e=None): self.app.show_frame(frame)
        def enter(e, w=card, c=color):
            w.config(bg=BG_CARD)
            for ch in w.winfo_children():
                try: ch.config(bg=BG_CARD)
                except: pass
        def leave(e, w=card):
            w.config(bg=BG_PANEL)
            for ch in w.winfo_children():
                try: ch.config(bg=BG_PANEL)
                except: pass

        for w in [card] + card.winfo_children():
            w.bind("<Button-1>", go)
            w.bind("<Enter>", enter)
            w.bind("<Leave>", leave)

    def _refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cb["values"] = ports
        if ports:
            self.port_var.set(ports[0])

    def _toggle(self):
        if self.conn_btn["text"].strip() == "CONECTAR":
            res = self.app.serial_mgr.connect(self.port_var.get(), self.baud_var.get())
            if res is True:
                self.conn_btn.config(text="  DESCONECTAR  ", bg=ACC_RED, fg="white")
                self.status_lbl.config(text=f"●  Conectado em {self.port_var.get()}",
                                        fg=ACC_GREEN)
                self.app.on_connect(self.port_var.get())
            else:
                messagebox.showerror("Erro de Conexão", str(res), parent=self)
        else:
            self.app.serial_mgr.disconnect()
            self.conn_btn.config(text="  CONECTAR  ", bg=ACC_GREEN, fg=BG_DARK)
            self.status_lbl.config(text="○  Desconectado", fg=TXT_MUTE)
            self.app.on_disconnect()


# ─── TELA: MONITORAMENTO ──────────────────────────────────────────────────────
class MonitorFrame(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self.app = app
        self._chart_started = False
        self._build()

    def _build(self):
        # ── Topbar ──
        topbar = tk.Frame(self, bg=BG_PANEL, height=44)
        topbar.pack(fill=tk.X)
        topbar.pack_propagate(False)
        tk.Label(topbar, text="  📊  PAINEL DE MONITORAMENTO", bg=BG_PANEL, fg=TXT_PRI,
                 font=("Helvetica", 11, "bold")).pack(side=tk.LEFT, padx=10)
        self.motor_pill = tk.Label(topbar, text="  ■  MOTOR PARADO  ",
                                    bg=ACC_RED, fg="white",
                                    font=("Helvetica", 9, "bold"), padx=8, pady=3)
        self.motor_pill.pack(side=tk.RIGHT, padx=16, pady=10)
        self.conn_pill = tk.Label(topbar, text="SEM SINAL", bg=BG_CARD, fg=TXT_MUTE,
                                   font=("Helvetica", 9, "bold"), padx=8, pady=3)
        self.conn_pill.pack(side=tk.RIGHT, padx=6, pady=10)

        # ── Body ──
        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=14, pady=10)

        # Left panel
        left = tk.Frame(body, bg=BG_DARK)
        left.pack(side=tk.LEFT, fill=tk.Y)

        # Gauges
        gauge_row = tk.Frame(left, bg=BG_DARK)
        gauge_row.pack()
        self.g_real = GaugeCanvas(gauge_row, "RPM REAL", "rpm", 2000,
                                   color=ACC_GREEN, size=175)
        self.g_real.grid(row=0, column=0, padx=6, pady=6)
        self.g_sp = GaugeCanvas(gauge_row, "SETPOINT", "rpm", 2000,
                                 color=ACC_BLUE, size=175)
        self.g_sp.grid(row=0, column=1, padx=6, pady=6)

        # Digital row
        digs = tk.Frame(left, bg=BG_DARK)
        digs.pack(pady=4)
        self.d_alvo = DigitDisplay(digs, "ALVO RPM", "rpm", color=ACC_CYAN)
        self.d_alvo.pack(side=tk.LEFT, padx=4)
        self.d_freq = DigitDisplay(digs, "FREQUÊNCIA", "Hz", color=ACC_AMBER)
        self.d_freq.pack(side=tk.LEFT, padx=4)
        self.d_corr = DigitDisplay(digs, "CORRENTE", "A", color=ACC_RED)
        self.d_corr.pack(side=tk.LEFT, padx=4)

        # Right: chart
        right = tk.Frame(body, bg=BG_CARD, padx=10, pady=10)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))

        tk.Label(right, text="HISTÓRICO RPM — Últimos 3 minutos",
                 bg=BG_CARD, fg=TXT_SEC, font=("Helvetica", 9, "bold")).pack(anchor="w", pady=(0, 4))

        fig, self.ax = plt.subplots(figsize=(5.5, 4.2))
        fig.patch.set_facecolor(BG_CARD)
        self.ax.set_facecolor("#161b22")
        self.ax.tick_params(colors=TXT_SEC, labelsize=8)
        for sp in self.ax.spines.values():
            sp.set_color(BORDER)
        self.ax.set_ylabel("RPM", color=TXT_SEC, fontsize=9)
        self.ax.set_xlabel("Tempo (s)", color=TXT_SEC, fontsize=9)
        self.ax.grid(True, color=BORDER, linewidth=0.5, alpha=0.6, linestyle="--")
        self.ax.set_ylim(0, 100)
        self.ax.set_xlim(0, 30)

        self.ln_real, = self.ax.plot([], [], color=ACC_GREEN, lw=2.0, label="Real")
        self.ln_sp,   = self.ax.plot([], [], color=ACC_BLUE,  lw=1.5, ls="--", label="Setpoint")
        self.ln_alvo, = self.ax.plot([], [], color=ACC_AMBER, lw=1.2, ls=":",  label="Alvo")
        self.ax.legend(loc="upper left", facecolor=BG_CARD, edgecolor=BORDER,
                       labelcolor=TXT_SEC, fontsize=8, framealpha=0.9)
        plt.tight_layout(pad=1.0)

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
            self.ln_alvo.set_data(xs, list(hist["alvo"]))
            self.ax.set_xlim(0, max(xs[-1], 30))
            all_v = list(hist["real"]) + list(hist["sp"]) + list(hist["alvo"])
            ymax = max(all_v) if all_v else 100
            self.ax.set_ylim(-20, ymax * 1.18 + 80)
            self.fig_canvas.draw_idle()
        self.after(800, self._tick_chart)

    def update_values(self, data):
        self.g_real.set_value(data["real"])
        self.g_sp.set_value(data["sp"])
        self.d_alvo.set(data["alvo"], "{:.0f}")
        self.d_freq.set(data["freq"], "{:.2f}")
        self.d_corr.set(data["corr"], "{:.1f}")
        if data["real"] > 15:
            self.motor_pill.config(text="  ▶  EM OPERAÇÃO  ", bg=ACC_GREEN, fg=BG_DARK)
        else:
            self.motor_pill.config(text="  ■  MOTOR PARADO  ", bg=ACC_RED, fg="white")

    def set_connected(self, connected):
        if connected:
            self.conn_pill.config(text="● ONLINE", bg="#1c3a2a", fg=ACC_GREEN)
        else:
            self.conn_pill.config(text="SEM SINAL", bg=BG_CARD, fg=TXT_MUTE)


# ─── TELA: CONTROLE ───────────────────────────────────────────────────────────
class ControlFrame(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self.app = app
        self.mode = tk.StringVar(value="rpm")
        self._build()
        self._update_status()

    def _build(self):
        # Topbar
        topbar = tk.Frame(self, bg=BG_PANEL, height=44)
        topbar.pack(fill=tk.X)
        topbar.pack_propagate(False)
        tk.Label(topbar, text="  🎛  PAINEL DE CONTROLE", bg=BG_PANEL, fg=TXT_PRI,
                 font=("Helvetica", 11, "bold")).pack(side=tk.LEFT, padx=10)
        self.mode_badge = tk.Label(topbar, text="MODO: CONTROLE PI — RPM",
                                    bg="#1c2e1c", fg=ACC_GREEN,
                                    font=("Helvetica", 9, "bold"), padx=10, pady=3)
        self.mode_badge.pack(side=tk.RIGHT, padx=16, pady=10)

        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)

        # ── Coluna Esquerda ──
        left = tk.Frame(body, bg=BG_DARK, width=360)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        # -- Modo --
        self._section(left, "MODO DE OPERAÇÃO")
        mode_card = tk.Frame(left, bg=BG_PANEL, padx=16, pady=14)
        mode_card.pack(fill=tk.X, pady=(0, 10))

        modes = [
            ("rpm",  "▶  CONTROLE PI — RPM",    "Controlador de velocidade ativo (recomendado)", ACC_GREEN),
            ("freq", "〜  MALHA ABERTA — Hz",    "Frequência direta ao inversor (sem realimentação)", ACC_AMBER),
        ]
        for val, lbl, desc, color in modes:
            rf = tk.Frame(mode_card, bg=BG_PANEL)
            rf.pack(anchor="w", pady=4)
            rb = tk.Radiobutton(rf, text=lbl, variable=self.mode, value=val,
                                bg=BG_PANEL, fg=TXT_PRI, activebackground=BG_PANEL,
                                selectcolor=BG_DARK, font=("Helvetica", 10, "bold"),
                                command=self._on_mode_change)
            rb.pack(side=tk.LEFT)
            tk.Label(rf, text=f"   {desc}", bg=BG_PANEL, fg=TXT_MUTE,
                     font=("Helvetica", 7)).pack(side=tk.LEFT)

        # -- Setpoint --
        self._section(left, "SETPOINT")
        sp_card = tk.Frame(left, bg=BG_PANEL, padx=16, pady=16)
        sp_card.pack(fill=tk.X, pady=(0, 10))

        self.sp_label = tk.Label(sp_card, text="Velocidade Desejada (RPM):",
                                  bg=BG_PANEL, fg=TXT_SEC, font=("Helvetica", 9))
        self.sp_label.pack(anchor="w")

        entry_row = tk.Frame(sp_card, bg=BG_PANEL)
        entry_row.pack(fill=tk.X, pady=8)

        self.sp_entry = tk.Entry(entry_row, font=("Courier New", 22, "bold"),
                                  bg=BG_INPUT, fg=ACC_GREEN, insertbackground=ACC_GREEN,
                                  relief=tk.FLAT, width=9, justify="center",
                                  highlightthickness=2,
                                  highlightcolor=ACC_BLUE,
                                  highlightbackground=BORDER)
        self.sp_entry.pack(side=tk.LEFT, ipady=4)
        self.sp_entry.insert(0, "0")

        self.unit_lbl = tk.Label(entry_row, text="RPM", bg=BG_PANEL, fg=TXT_SEC,
                                  font=("Helvetica", 14, "bold"))
        self.unit_lbl.pack(side=tk.LEFT, padx=12)

        # Slider
        self.slider_var = tk.DoubleVar(value=0)
        self.slider = tk.Scale(sp_card, from_=0, to=2000, orient=tk.HORIZONTAL,
                                variable=self.slider_var, bg=BG_PANEL, fg=TXT_SEC,
                                troughcolor=BG_INPUT, activebackground=ACC_BLUE,
                                highlightthickness=0, sliderlength=20, bd=0,
                                command=self._slider_moved,
                                font=("Helvetica", 7))
        self.slider.pack(fill=tk.X, pady=4)

        self.sp_entry.bind("<Return>", lambda e: (self._sync_from_entry(), self._send_sp()))
        self.sp_entry.bind("<FocusOut>", lambda e: self._sync_from_entry())

        send_btn = tk.Button(sp_card, text="  ENVIAR SETPOINT  ▶ ",
                              bg=ACC_BLUE, fg=BG_DARK, relief=tk.FLAT,
                              font=("Helvetica", 10, "bold"),
                              padx=10, pady=9, cursor="hand2",
                              command=self._send_sp)
        send_btn.pack(fill=tk.X, pady=(6, 0))

        # Nota malha aberta
        self.note_lbl = tk.Label(sp_card,
                                  text="⚠ Modo Malha Aberta requer atualização do firmware ESP32.\n"
                                       "  O comando será enviado como: freq:<valor>",
                                  bg=BG_PANEL, fg=ACC_AMBER,
                                  font=("Helvetica", 7, "italic"),
                                  justify="left")

        # -- Comandos Motor --
        self._section(left, "COMANDOS DO MOTOR")
        cmd_card = tk.Frame(left, bg=BG_PANEL, padx=16, pady=16)
        cmd_card.pack(fill=tk.X)

        cmd_row = tk.Frame(cmd_card, bg=BG_PANEL)
        cmd_row.pack()

        for text, color, fg, cmd in [
            ("▶ RUN",   ACC_GREEN, BG_DARK,  "run"),
            ("■ STOP",  ACC_RED,   "white",  "stop"),
            ("↺ RESET", ACC_AMBER, BG_DARK,  "reset"),
        ]:
            tk.Button(cmd_row, text=text, bg=color, fg=fg, relief=tk.FLAT,
                      font=("Helvetica", 10, "bold"), padx=18, pady=10,
                      cursor="hand2",
                      command=lambda c=cmd: self._send_cmd(c)
                      ).pack(side=tk.LEFT, padx=4)

        # ── Coluna Direita ──
        right = tk.Frame(body, bg=BG_DARK)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(14, 0))

        # Status cards
        self._section(right, "STATUS EM TEMPO REAL")
        grid_frame = tk.Frame(right, bg=BG_DARK)
        grid_frame.pack(fill=tk.X, pady=(0, 10))
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)
        grid_frame.columnconfigure(2, weight=1)

        self._status = {}
        status_cfg = [
            ("alvo", "ALVO",       "rpm", ACC_CYAN,   "{:.0f}"),
            ("sp",   "SETPOINT",   "rpm", ACC_BLUE,   "{:.1f}"),
            ("real", "RPM REAL",   "rpm", ACC_GREEN,  "{:.1f}"),
            ("freq", "FREQUÊNCIA", "Hz",  ACC_AMBER,  "{:.2f}"),
            ("corr", "CORRENTE",   "A",   ACC_RED,    "{:.1f}"),
        ]
        for i, (key, lbl, unit, color, fmt) in enumerate(status_cfg):
            card = tk.Frame(grid_frame, bg=BG_CARD, padx=14, pady=12)
            card.grid(row=i // 3, column=i % 3, padx=5, pady=5, sticky="nsew")
            # color strip top
            tk.Frame(card, bg=color, height=2).pack(fill=tk.X, pady=(0, 6))
            tk.Label(card, text=lbl, bg=BG_CARD, fg=TXT_SEC,
                     font=("Helvetica", 8, "bold")).pack(anchor="w")
            v_lbl = tk.Label(card, text="---", bg=BG_CARD, fg=color,
                              font=("Courier New", 18, "bold"))
            v_lbl.pack(anchor="w")
            tk.Label(card, text=unit, bg=BG_CARD, fg=TXT_MUTE,
                     font=("Helvetica", 7)).pack(anchor="w")
            self._status[key] = (v_lbl, fmt)

        # Log
        self._section(right, "LOG DE COMANDOS")
        log_frame = tk.Frame(right, bg=BG_CARD)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_txt = tk.Text(log_frame, bg=BG_CARD, fg=ACC_GREEN,
                                font=("Courier New", 9), relief=tk.FLAT,
                                state=tk.DISABLED, wrap=tk.WORD,
                                insertbackground=ACC_GREEN)
        sb = ttk.Scrollbar(log_frame, command=self.log_txt.yview)
        self.log_txt.config(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_txt.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.log_txt.tag_config("info",  foreground=ACC_GREEN)
        self.log_txt.tag_config("warn",  foreground=ACC_AMBER)
        self.log_txt.tag_config("error", foreground=ACC_RED)
        self.log_txt.tag_config("cmd",   foreground=ACC_CYAN)

    def _section(self, parent, title):
        row = tk.Frame(parent, bg=BG_DARK)
        row.pack(fill=tk.X, pady=(8, 3))
        tk.Label(row, text=f"  {title}", bg=BG_DARK, fg=TXT_MUTE,
                 font=("Helvetica", 8, "bold")).pack(side=tk.LEFT)
        tk.Frame(row, bg=BORDER, height=1).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

    def _on_mode_change(self):
        m = self.mode.get()
        if m == "rpm":
            self.sp_label.config(text="Velocidade Desejada (RPM):")
            self.unit_lbl.config(text="RPM")
            self.slider.config(to=2000)
            self.mode_badge.config(text="MODO: CONTROLE PI — RPM", bg="#1c2e1c", fg=ACC_GREEN)
            self.note_lbl.pack_forget()
        else:
            self.sp_label.config(text="Frequência Desejada (Hz):")
            self.unit_lbl.config(text="Hz")
            self.slider.config(to=60)
            self.mode_badge.config(text="MODO: MALHA ABERTA — Hz", bg="#2e2a14", fg=ACC_AMBER)
            self.note_lbl.pack(anchor="w", pady=(6, 0))
        self.sp_entry.delete(0, tk.END)
        self.sp_entry.insert(0, "0")
        self.slider_var.set(0)

    def _slider_moved(self, val):
        self.sp_entry.delete(0, tk.END)
        self.sp_entry.insert(0, f"{float(val):.1f}")

    def _sync_from_entry(self):
        try:
            self.slider_var.set(float(self.sp_entry.get()))
        except ValueError:
            pass

    def _send_sp(self):
        try:
            val = float(self.sp_entry.get())
            if self.mode.get() == "rpm":
                if not (0 <= val <= 2000):
                    self._log("Valor fora do intervalo (0–2000 RPM)", "error")
                    return
                self.app.serial_mgr.send(str(int(val)))
                self._log(f"Setpoint enviado: {val:.0f} RPM", "info")
            else:
                if not (0 <= val <= 60):
                    self._log("Valor fora do intervalo (0–60 Hz)", "error")
                    return
                # Quando o firmware for atualizado: self.app.serial_mgr.send(f"freq:{val}")
                self.app.serial_mgr.send(f"freq:{val:.1f}")
                self._log(f"Frequência enviada: {val:.1f} Hz  [Malha Aberta]", "warn")
        except ValueError:
            self._log("Valor inválido inserido.", "error")

    def _send_cmd(self, cmd):
        self.app.serial_mgr.send(cmd)
        self._log(f"Comando: {cmd.upper()}", "cmd")

    def _log(self, msg, kind="info"):
        ts = time.strftime("%H:%M:%S")
        self.log_txt.config(state=tk.NORMAL)
        self.log_txt.insert(tk.END, f"[{ts}] {msg}\n", kind)
        self.log_txt.see(tk.END)
        self.log_txt.config(state=tk.DISABLED)

    def _update_status(self):
        data = self.app.data
        for key, (lbl, fmt) in self._status.items():
            lbl.config(text=fmt.format(data.get(key, 0.0)))
        self.after(400, self._update_status)


# ─── APLICAÇÃO PRINCIPAL ──────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Motor Control SCADA — ESP32")
        self.geometry("1150x720")
        self.minsize(960, 640)
        self.configure(bg=BG_ROOT)

        self.data = {k: 0.0 for k in ("alvo", "sp", "real", "freq", "corr")}
        self.history = {k: deque(maxlen=MAX_PTS) for k in self.data}
        self.times = deque(maxlen=MAX_PTS)

        self.serial_mgr = SerialManager(
            on_data=self._on_data,
            on_log=lambda m, **kw: None
        )

        self._build_navbar()
        self._build_frames()
        self.show_frame("home")
        self._sync_monitor()

    def _build_navbar(self):
        nb = tk.Frame(self, bg=BG_PANEL, height=48)
        nb.pack(fill=tk.X)
        nb.pack_propagate(False)

        # Separator bottom
        tk.Frame(nb, bg=BORDER, height=1).place(relx=0, rely=1.0, anchor="sw", relwidth=1)

        tk.Label(nb, text=" ⚙ MOTOR SCADA", bg=BG_PANEL, fg=ACC_BLUE,
                 font=("Courier New", 12, "bold")).pack(side=tk.LEFT, padx=16)

        self.nav_conn = tk.Label(nb, text="○ OFFLINE", bg=BG_PANEL, fg=TXT_MUTE,
                                  font=("Helvetica", 9, "bold"))
        self.nav_conn.pack(side=tk.RIGHT, padx=18)

        sep = tk.Frame(nb, bg=BORDER, width=1)
        sep.pack(side=tk.RIGHT, fill=tk.Y, pady=10)

        for frame_id, label in [("home", "⌂  INÍCIO"),
                                  ("monitor", "📊  MONITORAMENTO"),
                                  ("control", "🎛  CONTROLE")]:
            btn = tk.Button(nb, text=label, bg=BG_PANEL, fg=TXT_SEC,
                            relief=tk.FLAT, font=("Helvetica", 9, "bold"),
                            activebackground=BG_CARD, activeforeground=TXT_PRI,
                            cursor="hand2", padx=14, pady=14,
                            command=lambda n=frame_id: self.show_frame(n))
            btn.pack(side=tk.LEFT)

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
        if name == "monitor":
            self.frames["monitor"].start_chart()

    def on_connect(self, port):
        self.nav_conn.config(text=f"● {port}", fg=ACC_GREEN)
        self.frames["monitor"].set_connected(True)

    def on_disconnect(self):
        self.nav_conn.config(text="○ OFFLINE", fg=TXT_MUTE)
        self.frames["monitor"].set_connected(False)

    def _on_data(self, data):
        self.data.update(data)
        self.times.append(time.time())
        for k, v in data.items():
            self.history[k].append(v)

    def _sync_monitor(self):
        self.frames["monitor"].update_values(self.data)
        self.after(500, self._sync_monitor)


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()