import pandas as pd
import matplotlib.pyplot as plt

# Lista com os nomes dos arquivos CSV na mesma pasta que o script
arquivos = [
    "DADOS_IC_15Hz.csv",
    "DADOS_IC_30Hz.csv",
    "DADOS_IC_45Hz.csv",
    "DADOS_IC_60Hz.csv"
]
titulos = ["15 Hz", "30 Hz", "45 Hz", "60 Hz"]

# Criando uma figura com 4 subplots (grid 2x2)
fig, axs = plt.subplots(2, 2, figsize=(12, 10))
axs = axs.flatten() # Transforma a matriz 2x2 num vetor de 4 posições para facilitar o loop

for i, arquivo in enumerate(arquivos):
    # Lendo o arquivo CSV com separador ponto e vírgula
    # on_bad_lines='skip' evita travar caso tenha alguma linha com formato quebrado
    df = pd.read_csv(arquivo, sep=';', on_bad_lines='skip')
    
    # Limpando possíveis espaços no nome das colunas
    df.columns = df.columns.str.strip()
    
    # Garantindo que as colunas essenciais existem antes de plotar
    if 'tempo_s' in df.columns and 'rpm_calibrado' in df.columns:
        axs[i].plot(df['tempo_s'], df['rpm_calibrado'], label='RPM Calibrado', color='#1f77b4', linewidth=2)
    
    if 'tempo_s' in df.columns and 'rpm_bruto' in df.columns:
        axs[i].plot(df['tempo_s'], df['rpm_bruto'], label='RPM Bruto', color='#ff7f0e', alpha=0.7, linestyle='--')
        
    # Ajustando título, eixos e legendas de cada gráfico individual
    axs[i].set_title(f'Resposta do Sistema - {titulos[i]}')
    axs[i].set_xlabel('Tempo (s)')
    axs[i].set_ylabel('Rotação (RPM)')
    axs[i].grid(True, linestyle=':', alpha=0.7)
    axs[i].legend()

# Ajusta o espaçamento entre os gráficos para não sobrepor os títulos
plt.tight_layout()

# Salva a imagem com alta resolução (opcional) e mostra o gráfico na tela
plt.savefig('graficos_rpm_resposta.png', dpi=300)
plt.show()