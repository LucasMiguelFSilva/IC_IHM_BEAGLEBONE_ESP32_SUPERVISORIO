# BeagleBone SCADA: IHM Embarcada com Display LCD

Este repositório contém o código-fonte em Python e a documentação técnica passo a passo para a implementação de um Sistema Supervisório (SCADA / Interface Homem-Máquina) rodando de forma autônoma em uma placa BeagleBone (Black/Green) equipada com um display LCD Touchscreen.

## 🎯 Objetivo do Projeto
Transformar uma BeagleBone em uma IHM industrial autônoma. O sistema operacional (Debian 11) foi otimizado para inicializar diretamente em uma interface gráfica Python em tela cheia (Kiosk mode), garantindo o controle do hardware sem a necessidade de periféricos externos ou intervenção manual no boot.

## 🛠️ Hardware Utilizado
* **Placa-mãe:** BeagleBone (Black / Green)
* **Display:** LCD Touchscreen resistivo/capacitivo (Driver `ti-tsc`)
* **Armazenamento:** Memória eMMC nativa (4GB) com suporte/expansão via MicroSD.
* **Alimentação:** Fonte 5V DC

## 💻 Software e Tecnologias
* **Sistema Operacional:** Debian 11 (Bullseye) com ambiente gráfico (XFCE/LightDM).
* **Linguagem Principal:** Python 3
* **Interface Gráfica:** (Tkinter, pyserial, matplotlib,threading, re, time, collections.)
* **Controle de Vídeo/Toque:** Servidor Xorg / X11 (`xinput-calibrator`).

## ⚙️ Principais Desafios e Soluções Abordadas
Este repositório documenta não apenas o código, mas as configurações de baixo nível no Linux necessárias para a estabilidade do sistema em um ambiente de automação industrial:
1. **Calibração de Toque (Touchscreen):** Correção de eixos invertidos e limites de alcance da tela via `CalibrationMatrix` no X11.
2. **Inicialização Automática (Autostart):** Configuração de arquivos `.desktop` para execução automática do script Python no boot do LightDM.
3. **Gerenciamento de Armazenamento:** Solução de problemas de loop de vídeo e travamento gráfico (erros de `FBIOPUTCMAP`) causados pela saturação da memória eMMC por logs do sistema.

## 📖 Como Usar / Guia de Instalação
O guia completo detalhando cada comando desde a gravação do cartão SD, configuração do painel, calibração do toque e instalação das dependências está disponível no arquivo:
👉 [Manual de Configuracao - BeagleBone.pdf](https://docs.google.com/document/d/1qPbW_UKzkaNFS0DHclRR7wraCRruQvw48oqZS8Dt150/edit?usp=sharing)

## 👨‍💻 Autores

**Lucas Miguel Francisco da Silva**
* Estudante de Engenharia de Controle e Automação - Universidade Federal de Uberlândia (UFU)
* Técnico em Automação Industrial - SENAI

**Pedro Victor Coelho Uga**
* Estudante de Engenharia de Controle e Automação - Universidade Federal de Uberlândia (UFU)

Sinta-se à vontade para abrir os *arquivos* ou enviar *pull requests* caso tenha dúvidas sobre a configuração do X11 ou do script Python na BeagleBone!
