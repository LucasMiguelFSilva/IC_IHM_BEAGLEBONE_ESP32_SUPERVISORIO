#include "Encoder.h"

// Inicializa a variável estática (compartilhada) de contagem de pulsos
volatile uint32_t Encoder::_pulsos = 0;

// Construtor: Chamado quando você cria o objeto 'Encoder'
Encoder::Encoder(int pinA, unsigned long pulsosPorRotacao) {
    // Salva as configurações passadas (pino e PPR) nas variáveis internas
    _pinA = pinA;
    _ppr = pulsosPorRotacao;
    
    // Inicializa as variáveis de estado
    _rpm = 0.0;
    _tempoAnterior = 0;
}

// Função da Interrupção (ISR): Roda no hardware toda vez que o pino A sobe
void IRAM_ATTR Encoder::_contarPulsosISR() {
    // Apenas incrementa o contador. Deve ser o mais rápido possível.
    _pulsos++;
}

// Função 'begin': Chamada uma vez no setup()
void Encoder::begin() {
    // Configura o pino do encoder como entrada
    pinMode(_pinA, INPUT);
    
    // Anexa a interrupção ao pino, define a função a ser chamada (_contarPulsosISR)
    // e o modo (RISING - borda de subida)
    attachInterrupt(digitalPinToInterrupt(_pinA), _contarPulsosISR, RISING);
    
    // ALTERADO: Inicializa o contador de tempo com millis()
    _tempoAnterior = millis();
}

// Função 'loop': Chamada continuamente no loop() principal
void Encoder::loop() {
    // ALTERADO: Pega o tempo atual em milissegundos
    unsigned long tempoAtualMillis = millis();

    // ALTERADO: Compara com a constante de tempo em milissegundos (500ms)
    if (tempoAtualMillis - _tempoAnterior >= _Ts_Encoder_ms) {
        
        _tempoAnterior = tempoAtualMillis; // Atualiza o tempo da última medição

        // --- Início da Seção Crítica ---
        // Copia e zera a contagem de pulsos de forma segura, 
        // desabilitando interrupções temporariamente para evitar corrupção de dados.
        uint32_t pulsosMedidos;
        noInterrupts();
        pulsosMedidos = _pulsos; 
        _pulsos = 0;       
        interrupts();
        // --- Fim da Seção Crítica ---

        // ALTERADO: Fórmula do RPM ajustada para usar milissegundos
        // (pulsosMedidos * 60 segundos * 1000 milissegundos) / (pulsos_por_rotacao * tempo_em_ms)
        _rpm = (pulsosMedidos * 60.0 * 1000.0) / (_ppr * _Ts_Encoder_ms);
    }
}

// Função 'getRPM': Usada pelo main.cpp para obter o último valor calculado
float Encoder::getRPM() {
    // Simplesmente retorna o último valor de RPM que foi calculado
    return _rpm;
}