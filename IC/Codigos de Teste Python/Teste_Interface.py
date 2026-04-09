"""
MOTOR CONTROL SCADA — ESP32 + Inversor Modbus
Sistema Supervisório Industrial — Python/Tkinter

Dependências: pip install pyserial matplotlib
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
            self.on_log(f"Conectado em {port}", kind="info")
            return True
        except Exception as e:
            return str(e)

    def disconnect(self):
        self.running = False
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
                self.on_log("Porta serial fechada", kind="info")
            except Exception:
                pass

    def send(self, msg: str):
        with self._lock:
            if self.ser and self.ser.is_open:
                try:
                    self.ser.write((msg.strip() + "\n").encode("utf-8"))
                    self.on_log(f"Enviado: {msg}", kind="cmd")
                except Exception as e:
                    self.on_log(f"[SERIAL ERR] {e}", kind="error")
            else:
                self.on_log(f"[SERIAL] Não conectado. Tentativa de enviar: {msg}", kind="warn")

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
                            # 1. Primeiro verificamos se é o pacote padrão de telemetria
                            m = self.PATTERN.search(text)
                            
                            if m:
                                # Se FOR telemetria, apenas atualizamos os mostradores (NÃO chamamos o on_log)
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
                                # 2. Se NÃO FOR telemetria (ex: "Motor RUN", "Conectado", erros), enviamos para o Log
                                self.on_log(text, kind="info")
            except Exception:
                pass
            time.sleep(0.02)


# ─── WIDGET: DISPLAY DIGITAL (GRANDE) ────────────────────────────────────────
class BigValueDisplay(tk.Frame):
    """Display grande para mostrar apenas o valor (sem gauge)."""
    def __init__(self, parent, label, unit, color=ACC_GREEN, **kw):
        super().__init__(parent, bg=BG_CARD, padx=12, pady=10, **kw)
        tk.Label(self, text=label, bg=BG_CARD, fg=TXT_SEC,
                 font=("Helvetica", 9, "bold")).pack(anchor="w")
        self._val = tk.Label(self, text="---", bg=BG_CARD, fg=color,
                              font=("Courier New", 36, "bold"))
        self._val.pack(anchor="center", pady=(6, 4))
        tk.Label(self, text=unit, bg=BG_CARD, fg=TXT_MUTE,
                 font=("Helvetica", 9)).pack(anchor="center")

    def set(self, val, fmt="{:.0f}"):
        try:
            self._val.config(text=fmt.format(val))
        except Exception:
            self._val.config(text=str(val))


# ─── WIDGET: DISPLAY DIGITAL (PEQUENO) ───────────────────────────────────────
class DigitDisplay(tk.Frame):
    def __init__(self, parent, label, unit, color=ACC_GREEN, wide=False, **kw):
        super().__init__(parent, bg=BG_CARD, padx=12 if wide else 10, pady=8, **kw)
        tk.Label(self, text=label, bg=BG_CARD, fg=TXT_SEC,
                 font=("Helvetica", 8, "bold")).pack(anchor="w")
        self._val = tk.Label(self, text="---", bg=BG_CARD, fg=color,
                              font=("Courier New", 18 if wide else 16, "bold"))
        self._val.pack(anchor="w", pady=(4, 2))
        tk.Label(self, text=unit, bg=BG_CARD, fg=TXT_MUTE,
                 font=("Helvetica", 7)).pack(anchor="w")

    def set(self, val, fmt="{:.1f}"):
        try:
            self._val.config(text=fmt.format(val))
        except Exception:
            self._val.config(text=str(val))


# ─── TELA: HOME ───────────────────────────────────────────────────────────────
class HomeFrame(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_ROOT)
        self.app = app
        self._build()

    def _build(self):
        grid_cv = tk.Canvas(self, bg=BG_ROOT, highlightthickness=0)
        grid_cv.place(relx=0, rely=0, relwidth=1, relheight=1)
        for i in range(0, 2000, 60):
            grid_cv.create_line(i, 0, i, 2000, fill="#111820", width=1)
            grid_cv.create_line(0, i, 2000, i, fill="#111820", width=1)

        wrapper = tk.Frame(self, bg=BG_ROOT)
        wrapper.place(relx=0.5, rely=0.5, anchor="center")

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

        tk.Frame(wrapper, bg=BORDER, height=1).pack(fill=tk.X, pady=22)

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

        self.status_lbl = tk.Label(conn_card, text="○  DESCONECTADO",
                                    bg=BG_PANEL, fg=TXT_MUTE,
                                    font=("Helvetica", 9, "bold"))
        self.status_lbl.pack(anchor="w", pady=(10, 0))

        tk.Frame(wrapper, bg=BORDER, height=1).pack(fill=tk.X, pady=22)

        nav_row = tk.Frame(wrapper, bg=BG_ROOT)
        nav_row.pack()

        cards_cfg = [
            ("📊", "MONITORAMENTO", "Dados em tempo real\nValores · Gráficos · Status", "monitor", ACC_BLUE),
            ("🎛", "CONTROLE", "Comandos ao motor\nRPM · Frequência · RUN/STOP", "control", ACC_AMBER),
        ]
        for icon, title, desc, frame, color in cards_cfg:
            self._nav_card(nav_row, icon, title, desc, frame, color)

    def _nav_card(self, parent, icon, title, desc, frame, color):
        card = tk.Frame(parent, bg=BG_PANEL, padx=28, pady=20, cursor="hand2")
        card.pack(side=tk.LEFT, padx=12)

        tk.Label(card, text=icon, bg=BG_PANEL, fg=color,
                 font=("Helvetica", 30)).pack()
        tk.Label(card, text=title, bg=BG_PANEL, fg=TXT_PRI,
                 font=("Helvetica", 12, "bold")).pack(pady=(6, 2))
        tk.Label(card, text=desc, bg=BG_PANEL, fg=TXT_SEC,
                 font=("Helvetica", 8), justify="center").pack()

        accent = tk.Frame(card, bg=color, height=2)
        accent.pack(fill=tk.X, pady=(12, 0))

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


# ─── TELA: MONITORAMENTO (VALORES TEXTUAIS) ──────────────────────────────────
class MonitorFrame(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self.app = app
        self._chart_started = False
        self._build()

    def _build(self):
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

        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Left: coluna de valores textuais (preenchida verticalmente)
        left = tk.Frame(body, bg=BG_DARK, width=520)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        # Top: dois displays grandes (RPM REAL e SETPOINT) empilhados para preencher
        top_values = tk.Frame(left, bg=BG_DARK)
        top_values.pack(fill=tk.X, pady=(6, 8))
        self.display_real = BigValueDisplay(top_values, "RPM REAL", "rpm", color=ACC_GREEN)
        self.display_real.pack(fill=tk.X, padx=6, pady=(0, 8))
        self.display_sp = BigValueDisplay(top_values, "SETPOINT", "rpm", color=ACC_BLUE)
        self.display_sp.pack(fill=tk.X, padx=6, pady=(0, 8))

        # Middle: status menores distribuídos verticalmente para preencher o restante
        status_col = tk.Frame(left, bg=BG_DARK)
        status_col.pack(fill=tk.BOTH, expand=True, pady=(6, 6))

        status_cfg = [
            ("alvo", "ALVO",       "rpm", ACC_CYAN,   "{:.0f}"),
            ("freq", "FREQUÊNCIA", "Hz",  ACC_AMBER,  "{:.2f}"),
            ("corr", "CORRENTE",   "A",   ACC_RED,    "{:.1f}"),
            ("real_small", "RPM REAL (mini)", "rpm", ACC_GREEN, "{:.1f}"),
            ("sp_small", "SETPOINT (mini)", "rpm", ACC_BLUE, "{:.1f}"),
        ]
        self._status = {}
        for key, lbl, unit, color, fmt in status_cfg:
            card = tk.Frame(status_col, bg=BG_CARD, padx=10, pady=8)
            card.pack(fill=tk.X, padx=6, pady=6)
            tk.Frame(card, bg=color, height=3).pack(fill=tk.X, pady=(0, 8))
            tk.Label(card, text=lbl, bg=BG_CARD, fg=TXT_SEC,
                     font=("Helvetica", 9, "bold")).pack(anchor="w")
            v_lbl = tk.Label(card, text="---", bg=BG_CARD, fg=color,
                              font=("Courier New", 18, "bold"))
            v_lbl.pack(anchor="w")
            tk.Label(card, text=unit, bg=BG_CARD, fg=TXT_MUTE,
                     font=("Helvetica", 8)).pack(anchor="w")
            self._status[key] = (v_lbl, fmt)

        # Right: gráfico ocupa todo o espaço vertical
        right = tk.Frame(body, bg=BG_CARD, padx=10, pady=10)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 8))

        tk.Label(right, text="HISTÓRICO RPM — Últimos 3 minutos",
                 bg=BG_CARD, fg=TXT_SEC, font=("Helvetica", 9, "bold")).pack(anchor="w", pady=(0, 6))

        fig, self.ax = plt.subplots(figsize=(7.5, 5.2))
        fig.patch.set_facecolor(BG_CARD)
        self.ax.set_facecolor("#161b22")
        self.ax.tick_params(colors=TXT_SEC, labelsize=9)
        for sp in self.ax.spines.values():
            sp.set_color(BORDER)
        self.ax.set_ylabel("RPM", color=TXT_SEC, fontsize=10)
        self.ax.set_xlabel("Tempo (s)", color=TXT_SEC, fontsize=10)
        self.ax.grid(True, color=BORDER, linewidth=0.5, alpha=0.6, linestyle="--")
        self.ax.set_ylim(0, 100)
        self.ax.set_xlim(0, 30)

        self.ln_real, = self.ax.plot([], [], color=ACC_GREEN, lw=2.4, label="Real")
        self.ln_sp,   = self.ax.plot([], [], color=ACC_BLUE,  lw=1.8, ls="--", label="Setpoint")
        self.ln_alvo, = self.ax.plot([], [], color=ACC_AMBER, lw=1.4, ls=":",  label="Alvo")
        self.ax.legend(loc="upper left", facecolor=BG_CARD, edgecolor=BORDER,
                       labelcolor=TXT_SEC, fontsize=9, framealpha=0.95)
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
        self.after(700, self._tick_chart)

    def update_values(self, data):
        # big textual displays
        self.display_real.set(data.get("real", 0.0), "{:.0f}")
        self.display_sp.set(data.get("sp", 0.0), "{:.0f}")
        # small status cards
        self._status["alvo"][0].config(text=self._status["alvo"][1].format(data.get("alvo", 0.0)))
        self._status["freq"][0].config(text=self._status["freq"][1].format(data.get("freq", 0.0)))
        self._status["corr"][0].config(text=self._status["corr"][1].format(data.get("corr", 0.0)))
        self._status["real_small"][0].config(text=self._status["real_small"][1].format(data.get("real", 0.0)))
        self._status["sp_small"][0].config(text=self._status["sp_small"][1].format(data.get("sp", 0.0)))
        if data.get("real", 0.0) > 15:
            self.motor_pill.config(text="  ▶  EM OPERAÇÃO  ", bg=ACC_GREEN, fg=BG_DARK)
        else:
            self.motor_pill.config(text="  ■  MOTOR PARADO  ", bg=ACC_RED, fg="white")

    def set_connected(self, connected):
        if connected:
            self.conn_pill.config(text="● ONLINE", bg="#1c3a2a", fg=ACC_GREEN)
        else:
            self.conn_pill.config(text="SEM SINAL", bg=BG_CARD, fg=TXT_MUTE)


# ─── TELA: CONTROLE (DISTRIBUIÇÃO MELHORADA + LOG REDUZIDO) ────────────────
class ControlFrame(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_DARK)
        self.app = app
        self.mode = tk.StringVar(value="rpm")
        self.log_collapsed = tk.BooleanVar(value=False)
        self._log_history = deque(maxlen=500)
        self._build()
        self._update_status()

    def _build(self):
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
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # Layout em duas colunas: esquerda para setpoint/comandos, direita para status+log (log reduzido)
        left = tk.Frame(body, bg=BG_DARK, width=420)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        right = tk.Frame(body, bg=BG_DARK)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))

        # LEFT: Setpoint e Comandos (organizados verticalmente, ocupando bem o espaço)
        self._section(left, "SETPOINT")
        sp_card = tk.Frame(left, bg=BG_PANEL, padx=16, pady=14)
        sp_card.pack(fill=tk.X, pady=(0, 12))

        self.sp_label = tk.Label(sp_card, text="Velocidade Desejada (RPM):",
                                  bg=BG_PANEL, fg=TXT_SEC, font=("Helvetica", 9))
        self.sp_label.pack(anchor="w")

        entry_row = tk.Frame(sp_card, bg=BG_PANEL)
        entry_row.pack(fill=tk.X, pady=8)

        self.sp_entry = tk.Entry(entry_row, font=("Courier New", 26, "bold"),
                                  bg=BG_INPUT, fg=ACC_GREEN, insertbackground=ACC_GREEN,
                                  relief=tk.FLAT, width=8, justify="center",
                                  highlightthickness=2,
                                  highlightcolor=ACC_BLUE,
                                  highlightbackground=BORDER)
        self.sp_entry.pack(side=tk.LEFT, ipady=6)
        self.sp_entry.insert(0, "0")

        self.unit_lbl = tk.Label(entry_row, text="RPM", bg=BG_PANEL, fg=TXT_SEC,
                                  font=("Helvetica", 14, "bold"))
        self.unit_lbl.pack(side=tk.LEFT, padx=12)

        # Slider (compacto)
        self.slider_var = tk.DoubleVar(value=0)
        self.slider = tk.Scale(sp_card, from_=0, to=2000, orient=tk.HORIZONTAL,
                                variable=self.slider_var, bg=BG_PANEL, fg=TXT_SEC,
                                troughcolor=BG_INPUT, activebackground=ACC_BLUE,
                                highlightthickness=0, sliderlength=18, bd=0,
                                command=self._slider_moved,
                                font=("Helvetica", 8))
        self.slider.pack(fill=tk.X, pady=6)

        send_btn = tk.Button(sp_card, text="  ENVIAR SETPOINT  ▶ ",
                              bg=ACC_BLUE, fg=BG_DARK, relief=tk.FLAT,
                              font=("Helvetica", 11, "bold"),
                              padx=10, pady=10, cursor="hand2",
                              command=self._send_sp)
        send_btn.pack(fill=tk.X, pady=(6, 0))

        # Comandos do motor (botões maiores e alinhados)
        self._section(left, "COMANDOS DO MOTOR")
        cmd_card = tk.Frame(left, bg=BG_PANEL, padx=16, pady=14)
        cmd_card.pack(fill=tk.X, pady=(0, 12))

        cmd_row = tk.Frame(cmd_card, bg=BG_PANEL)
        cmd_row.pack(fill=tk.X)

        btn_run = tk.Button(cmd_row, text="▶ RUN", bg=ACC_GREEN, fg=BG_DARK,
                            relief=tk.FLAT, font=("Helvetica", 12, "bold"),
                            padx=18, pady=10, cursor="hand2",
                            command=lambda: self._send_cmd("run"))
        btn_run.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0,6))

        btn_stop = tk.Button(cmd_row, text="■ STOP", bg=ACC_RED, fg="white",
                             relief=tk.FLAT, font=("Helvetica", 12, "bold"),
                             padx=18, pady=10, cursor="hand2",
                             command=lambda: self._send_cmd("stop"))
        btn_stop.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=6)

        btn_reset = tk.Button(cmd_row, text="↺ RESET", bg=ACC_AMBER, fg=BG_DARK,
                              relief=tk.FLAT, font=("Helvetica", 12, "bold"),
                              padx=18, pady=10, cursor="hand2",
                              command=lambda: self._send_cmd("reset"))
        btn_reset.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(6,0))

        # Mode selection compact
        self._section(left, "MODO DE OPERAÇÃO")
        mode_card = tk.Frame(left, bg=BG_PANEL, padx=12, pady=10)
        mode_card.pack(fill=tk.X)
        rf = tk.Frame(mode_card, bg=BG_PANEL)
        rf.pack(anchor="w")
        rb1 = tk.Radiobutton(rf, text="▶ CONTROLE PI — RPM", variable=self.mode, value="rpm",
                             bg=BG_PANEL, fg=TXT_PRI, selectcolor=BG_DARK, font=("Helvetica", 10, "bold"),
                             command=self._on_mode_change)
        rb1.pack(anchor="w")
        rb2 = tk.Radiobutton(rf, text="〜 MALHA ABERTA — Hz", variable=self.mode, value="freq",
                             bg=BG_PANEL, fg=TXT_PRI, selectcolor=BG_DARK, font=("Helvetica", 10, "bold"),
                             command=self._on_mode_change)
        rb2.pack(anchor="w")

        # RIGHT: status (top) + log reduzido (bottom)
        status_area = tk.Frame(right, bg=BG_DARK)
        status_area.pack(fill=tk.BOTH, expand=True)

        self._section(status_area, "STATUS EM TEMPO REAL")
        grid_frame = tk.Frame(status_area, bg=BG_DARK)
        grid_frame.pack(fill=tk.X, pady=(0, 8))
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
            card = tk.Frame(grid_frame, bg=BG_CARD, padx=10, pady=8)
            card.grid(row=i // 3, column=i % 3, padx=6, pady=6, sticky="nsew")
            tk.Frame(card, bg=color, height=3).pack(fill=tk.X, pady=(0, 8))
            tk.Label(card, text=lbl, bg=BG_CARD, fg=TXT_SEC,
                     font=("Helvetica", 8, "bold")).pack(anchor="w")
            v_lbl = tk.Label(card, text="---", bg=BG_CARD, fg=color,
                              font=("Courier New", 18, "bold"))
            v_lbl.pack(anchor="w")
            tk.Label(card, text=unit, bg=BG_CARD, fg=TXT_MUTE,
                     font=("Helvetica", 7)).pack(anchor="w")
            self._status[key] = (v_lbl, fmt)

        # Log reduzido (metade do tamanho visual)
        self._section(status_area, "LOG DE COMANDOS")
        log_container = tk.Frame(status_area, bg=BG_CARD)
        log_container.pack(fill=tk.X, expand=False)

        log_header = tk.Frame(log_container, bg=BG_CARD)
        log_header.pack(fill=tk.X)
        tk.Label(log_header, text="Últimas ações (compacto)", bg=BG_CARD, fg=TXT_SEC, font=("Helvetica", 9, "bold")).pack(side=tk.LEFT, padx=6, pady=6)
        self.log_toggle_btn = tk.Button(log_header, text="⇩", bg=BG_INPUT, fg=TXT_PRI, relief=tk.FLAT, command=self._toggle_log, cursor="hand2")
        self.log_toggle_btn.pack(side=tk.RIGHT, padx=6, pady=6)

        self._log_frame = tk.Frame(log_container, bg=BG_CARD, height=110)
        self._log_frame.pack(fill=tk.X, padx=6, pady=(0,6))
        self._log_frame.pack_propagate(False)

        self.log_txt = tk.Text(self._log_frame, bg=BG_CARD, fg=ACC_GREEN,
                                font=("Courier New", 10), relief=tk.FLAT,
                                state=tk.DISABLED, wrap=tk.WORD, height=6,
                                insertbackground=ACC_GREEN)
        sb = ttk.Scrollbar(self._log_frame, command=self.log_txt.yview)
        self.log_txt.config(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_txt.pack(fill=tk.BOTH, expand=True)

        self.log_txt.tag_config("info", foreground=ACC_GREEN)
        self.log_txt.tag_config("warn", foreground=ACC_AMBER)
        self.log_txt.tag_config("error", foreground=ACC_RED)
        self.log_txt.tag_config("cmd", foreground=ACC_CYAN)

    def _toggle_log(self):
        if self.log_collapsed.get():
            self.log_collapsed.set(False)
            self._log_frame.pack(fill=tk.X, padx=6, pady=(0,6))
            self.log_toggle_btn.config(text="⇩")
        else:
            self.log_collapsed.set(True)
            self._log_frame.forget()
            self.log_toggle_btn.config(text="⇧")

    def append_log(self, text, kind="info"):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {text}"
        self._log_history.append((line, kind))
        # mostrar menos linhas (log reduzido): exibir últimas 6 linhas
        visible_lines = list(self._log_history)[-6:]
        self.log_txt.config(state=tk.NORMAL)
        self.log_txt.delete("1.0", tk.END)
        for ln, k in visible_lines:
            self.log_txt.insert(tk.END, ln + "\n", k)
        self.log_txt.see(tk.END)
        self.log_txt.config(state=tk.DISABLED)

    def _log(self, msg, kind="info"):
        self.append_log(msg, kind)

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
        else:
            self.sp_label.config(text="Frequência Desejada (Hz):")
            self.unit_lbl.config(text="Hz")
            self.slider.config(to=60)
            self.mode_badge.config(text="MODO: MALHA ABERTA — Hz", bg="#2e2a14", fg=ACC_AMBER)
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
                self.app.serial_mgr.send(f"freq:{val:.1f}")
                self._log(f"Frequência enviada: {val:.1f} Hz  [Malha Aberta]", "warn")
        except ValueError:
            self._log("Valor inválido inserido.", "error")

    def _send_cmd(self, cmd):
        self.app.serial_mgr.send(cmd)
        self._log(f"Comando: {cmd.upper()}", "cmd")

    def _update_status(self):
        data = self.app.data
        for key, (lbl, fmt) in self._status.items():
            lbl.config(text=fmt.format(data.get(key, 0.0)))
        self.after(400, self._update_status)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Motor Control SCADA — ESP32")
        self.geometry("1280x800")
        self.minsize(1024, 700)
        self.configure(bg=BG_ROOT)

        self.data = {k: 0.0 for k in ("alvo", "sp", "real", "freq", "corr")}
        self.history = {k: deque(maxlen=MAX_PTS) for k in self.data}
        self.times = deque(maxlen=MAX_PTS)

        self.serial_mgr = SerialManager(
            on_data=self._on_data,
            on_log=self._on_log
        )

        self._build_navbar()
        self._build_frames()
        self.show_frame("monitor")
        self._sync_monitor()

    def _build_navbar(self):
        nb = tk.Frame(self, bg=BG_PANEL, height=48)
        nb.pack(fill=tk.X)
        nb.pack_propagate(False)

        tk.Frame(nb, bg=BORDER, height=1).place(relx=0, rely=1.0, anchor="sw", relwidth=1)

        tk.Label(nb, text=" ⚙ MOTOR SCADA", bg=BG_PANEL, fg=ACC_BLUE,
                 font=("Courier New", 12, "bold")).pack(side=tk.LEFT, padx=16)

        self.nav_conn = tk.Label(nb, text="○ OFFLINE", bg=BG_PANEL, fg=TXT_MUTE,
                                  font=("Helvetica", 9, "bold"))
        self.nav_conn.pack(side=tk.RIGHT, padx=18)

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
        if "control" in self.frames:
            self.frames["control"].append_log(f"Conectado em {port}", "info")

    def on_disconnect(self):
        self.nav_conn.config(text="○ OFFLINE", fg=TXT_MUTE)
        self.frames["monitor"].set_connected(False)
        if "control" in self.frames:
            self.frames["control"].append_log("Desconectado", "warn")

    def _on_data(self, data):
        self.data.update(data)
        self.times.append(time.time())
        for k, v in data.items():
            self.history[k].append(v)

    def _on_log(self, message, kind="info"):
        try:
            if "control" in self.frames:
                self.frames["control"].append_log(message, kind)
        except Exception:
            pass

    def _sync_monitor(self):
        self.frames["monitor"].update_values(self.data)
        self.after(400, self._sync_monitor)


if __name__ == "__main__":
    app = App()
    app.mainloop()
