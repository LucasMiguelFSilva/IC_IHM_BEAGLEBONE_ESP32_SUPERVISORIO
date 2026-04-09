#include <Arduino.h>

// =====================================================
//         VARIÁVEIS DE ESTADO E COMANDOS
// =====================================================
#define CMD_RUN 1
#define CMD_STOP 6
#define CMD_RESET 7

uint16_t frequenciaDesejada_raw = 0;
uint16_t comandoMotorDesejado = CMD_STOP;

// =====================================================
//         VARIÁVEIS DE CONTROLE E MODOS
// =====================================================
bool modoMalhaFechada = true; // true = PI (RPM), false = Malha Aberta (Hz)
float FREQ_ALVO = 0.0;        // Frequencia alvo para malha aberta

// Gerador de Rampa (Malha Fechada)
float RPM_ALVO = 0.0;     
float RPM_SETPOINT = 0.0; 
#define PASSO_RAMPA_RPM 60.0  // 300 RPM/s em ciclos de 200ms

// Controlador PI Discreto
#define TS 0.2 
#define KP 0.02000000 
#define I_GAIN 0.020693305
#define B0 (KP + I_GAIN * TS)
#define B1 (-KP)

float ek = 0, ek_1 = 0;
float uk = 0, uk_1 = 0;

float controladorPI(float rpmAtual) {
    ek = RPM_SETPOINT - rpmAtual;
    uk = uk_1 + B0*ek + B1*ek_1;

    // Saturação (Anti-windup simples: limita uk_1)
    if(uk > 60.0) uk = 60.0; 
    if(uk < 0.0)  uk = 0.0;

    uk_1 = uk;
    ek_1 = ek;
    return uk;
}

// =====================================================
//         VARIÁVEIS DA SIMULAÇÃO FÍSICA
// =====================================================
float rpmRealSimulado = 0.0;
float correnteSimulada = 0.0;

// ---------------- SERIAL NÃO-BLOQUEANTE ----------------
void checkSerial() {
    static String inputBuffer = "";
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n') { 
            inputBuffer.trim();
            inputBuffer.toLowerCase();

            if (inputBuffer == "run") {
                comandoMotorDesejado = CMD_RUN;
                Serial.println(">>> COMANDO: RUN");
            } 
            else if (inputBuffer == "stop") {
                comandoMotorDesejado = CMD_STOP;
                Serial.println(">>> COMANDO: STOP");
            } 
            else if (inputBuffer == "reset") {
                comandoMotorDesejado = CMD_RESET;
                Serial.println(">>> COMANDO: RESET");
            } 
            else if (inputBuffer.startsWith("rpm:")) {
                float novoAlvo = inputBuffer.substring(4).toFloat();
                if (novoAlvo >= 0 && novoAlvo <= 2000) {
                    RPM_ALVO = novoAlvo;
                    FREQ_ALVO = 0; 
                    modoMalhaFechada = true;
                    Serial.printf(">>> MODO: RPM | ALVO: %.2f RPM\n", RPM_ALVO);
                }
            }
            else if (inputBuffer.startsWith("freq:")) {
                float novoAlvo = inputBuffer.substring(5).toFloat();
                if (novoAlvo >= 0 && novoAlvo <= 60) {
                    FREQ_ALVO = novoAlvo;
                    RPM_ALVO = 0; 
                    modoMalhaFechada = false;
                    Serial.printf(">>> MODO: FREQ | ALVO: %.2f Hz\n", FREQ_ALVO);
                }
            }
            inputBuffer = ""; 
        } else if (c != '\r') {
            inputBuffer += c;
        }
    }
}

// ---------------- RELATÓRIO SERIAL (PARA O PYTHON) ----------------
void imprimirDados() {
    // O texto deve bater EXATAMENTE com o Regex do Python (mantendo o "[Satus]")
    Serial.printf("[Status] Alvo: %.0f | SP: %.1f | Real: %.1f | Out: %.2f Hz | I: %.1f A\n",
                  RPM_ALVO, RPM_SETPOINT, rpmRealSimulado, (frequenciaDesejada_raw / 100.0), correnteSimulada);
}

// =====================================================
//         TASK DE CONTROLE & SIMULAÇÃO (CORE 1)
// =====================================================
void TaskControle(void *pvParameters) {
    unsigned long ultimoPrint = 0;

    for(;;) {
        // =================================================
        // 1. SIMULAÇÃO DA PLANTA (INVERSOR + MOTOR FÍSICO)
        // =================================================
        float freq_hz = frequenciaDesejada_raw / 100.0;
        float rpm_nominal_inversor = freq_hz * 30.0; // Assume motor 4 polos: 60Hz = 1800 RPM

        if(comandoMotorDesejado == CMD_RUN) {
            // Simula a inércia do motor: ele persegue o RPM ditado pela frequência do inversor com um leve atraso
            rpmRealSimulado += (rpm_nominal_inversor - rpmRealSimulado) * 0.15; 
            
            // Simula uma leitura de corrente (base de 1.2A vazio + extra de acordo com RPM + ruído randômico)
            if (rpmRealSimulado > 15) {
                correnteSimulada = 1.2 + (rpmRealSimulado / 2000.0) * 4.5 + (random(-15, 15) / 100.0);
            } else {
                correnteSimulada = 0.0;
            }
        } 
        else {
            // Desaceleração livre do motor ao parar
            rpmRealSimulado -= rpmRealSimulado * 0.08;
            if (rpmRealSimulado < 2.0) rpmRealSimulado = 0.0;
            correnteSimulada = 0.0;
        }


        // =================================================
        // 2. LÓGICA DE CONTROLE (PI E MALHAS)
        // =================================================
        if(comandoMotorDesejado == CMD_RUN) {
            
            if (modoMalhaFechada) {
                // --- MODO 1: MALHA FECHADA (Controle PI + Rampa) ---
                if (RPM_SETPOINT < RPM_ALVO) {
                    RPM_SETPOINT += PASSO_RAMPA_RPM;
                    if (RPM_SETPOINT > RPM_ALVO) RPM_SETPOINT = RPM_ALVO;
                } 
                else if (RPM_SETPOINT > RPM_ALVO) {
                    RPM_SETPOINT -= PASSO_RAMPA_RPM;
                    if (RPM_SETPOINT < RPM_ALVO) RPM_SETPOINT = RPM_ALVO;
                }

                // O PI recebe o RPM falso gerado pela simulação física e calcula a frequencia nova
                float freqCalculada = controladorPI(rpmRealSimulado);
                
                // Aplica Ganho de Compensação
                frequenciaDesejada_raw = (uint16_t)(freqCalculada * 1.3333 * 100.0);
            } 
            else {
                // --- MODO 2: MALHA ABERTA (Frequência Direta) ---
                uk_1 = 0; ek_1 = 0; 
                RPM_SETPOINT = 0;
                frequenciaDesejada_raw = (uint16_t)(FREQ_ALVO * 100.0);
            }

        } 
        else {
            frequenciaDesejada_raw = 0;
            RPM_SETPOINT = 0;
            uk_1 = 0; ek_1 = 0;
        }

        // Imprime dados para o SCADA atualizar gráficos a cada 200ms
        if (millis() - ultimoPrint >= 200) {
            imprimirDados();
            ultimoPrint = millis();
        }

        vTaskDelay(pdMS_TO_TICKS(200)); 
    }
}

// ---------------- SETUP ----------------
void setup() {
    Serial.begin(115200);

    // Inicializa a semente aleatória baseada no ruído de um pino flutuante para a simulação da corrente
    randomSeed(analogRead(0));

    // Task de controle e simulação rodando em core dedicado
    xTaskCreatePinnedToCore(TaskControle, "TaskControle", 4096, NULL, 1, NULL, 1);

    Serial.println("--- Modo Simulação Iniciado ---");
    Serial.println("Nenhum hardware Modbus ou Encoder necessário.");
}

// ---------------- LOOP PRINCIPAL ----------------
void loop() {
    checkSerial(); // Verifica os comandos do Python
    delay(20);     // Pequeno respiro para o watchdog timer
}