import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ==========================================
# 1. CONFIGURAÇÃO DOS ENSAIOS
# ==========================================
# Lista com o nome do arquivo e o degrau (Hz) que foi aplicado nele
ensaios = [
    {"arquivo": "Ensaio15Hz6s.csv", "degrau_hz": 15.0, "cor": "blue"},
    {"arquivo": "Ensaio30Hz6s.csv", "degrau_hz": 30.0, "cor": "green"},
    {"arquivo": "Ensaio45Hz6s.csv", "degrau_hz": 45.0, "cor": "orange"},
    {"arquivo": "Ensaio60Hz6s.csv", "degrau_hz": 60.0, "cor": "red"}
]

resultados = []

print("=== INICIANDO ANÁLISE EM LOTE DAS PLANTAS ===")

plt.figure(figsize=(12, 7))

# ==========================================
# 2. LOOP DE PROCESSAMENTO
# ==========================================
for ensaio in ensaios:
    arquivo = ensaio["arquivo"]
    degrau = ensaio["degrau_hz"]
    cor = ensaio["cor"]
    
    try:
        # Lê o CSV (O ESP32 salva com separador ';')
        df = pd.read_csv(arquivo, sep=';')
        df.columns = df.columns.str.strip() # Limpa espaços nos nomes das colunas
        
        t = df['tempo_s'].values
        rpm = df['rpm_calibrado'].values
        
        # --- MATEMÁTICA ---
        # RPM em Regime Permanente (Média dos últimos 50 pontos)
        rpm_max = np.mean(rpm[-50:])
        
        # Ganho (K)
        K = rpm_max / degrau
        
        # Encontra o instante do degrau (onde RPM passou de 1% do máximo)
        idx_start = np.where(rpm > 0.01 * rpm_max)[0]
        if len(idx_start) == 0:
            continue
        t_start = t[idx_start[0]]
        
        # Encontra os 63.2% para o Tau
        rpm_63 = 0.632 * rpm_max
        idx_63 = np.where(rpm >= rpm_63)[0][0]
        t_63 = t[idx_63]
        
        tau = t_63 - t_start
        
        # Salva o resultado na lista
        resultados.append({
            "Frequência": f"{degrau} Hz",
            "RPM Final": round(rpm_max, 2),
            "Ganho (K)": round(K, 4),
            "Tau (s)": round(tau, 2)
        })
        
        # --- PLOTAGEM ---
        plt.plot(t, rpm, color=cor, linewidth=2, label=f'Curva {degrau} Hz')
        
        # Plota um pontinho marcando onde fica o Tau (63.2%) em cada curva
        plt.plot(t_63, rpm_63, marker='o', markersize=8, color=cor)
        plt.text(t_63 + 0.5, rpm_63 - 50, f'Tau={tau:.1f}s', color=cor, fontweight='bold')
        
        print(f"[OK] {arquivo} processado com sucesso.")

    except FileNotFoundError:
        print(f"[ERRO] Arquivo '{arquivo}' não encontrado na pasta.")
    except Exception as e:
        print(f"[ERRO] Falha ao processar '{arquivo}': {e}")

# ==========================================
# 3. EXIBIÇÃO DA TABELA DE RESULTADOS
# ==========================================
print("\n" + "="*55)
print(f"{'Freq (Hz)':<12} | {'RPM Final':<10} | {'Ganho (K)':<10} | {'Tau (s)':<10}")
print("-" * 55)

for res in resultados:
    print(f"{res['Frequência']:<12} | {res['RPM Final']:<10} | {res['Ganho (K)']:<10} | {res['Tau (s)']:<10}")

print("="*55 + "\n")

# ==========================================
# 4. CONFIGURAÇÕES FINAIS DO GRÁFICO
# ==========================================
plt.title('Comparação da Resposta ao Degrau (Múltiplas Frequências)', fontsize=14, fontweight='bold')
plt.xlabel('Tempo (Segundos)', fontsize=12)
plt.ylabel('Velocidade (RPM)', fontsize=12)
plt.grid(True, linestyle='--', alpha=0.7)
plt.legend(loc='upper left')

print("Gerando gráfico comparativo. Feche a janela para encerrar.")
plt.show()