#ifndef ENCODER_H
#define ENCODER_H
#include <Arduino.h>
class Encoder {
public:
    //Especifica o pino do canal A e os pulsos por rotação
    Encoder(int pinA, unsigned long pulsosPorRotacao);
    // Método de inicialização (para ser chamado no setup())
    void begin();
    // Método de atualização (para ser chamado em CADA loop()) Ele verifica se é hora de calcular o RPM
    void loop();
    //Obtêm o último RPM calculado
    float getRPM();
private:
    // Pinos e configurações guardadas
    int _pinA;
    unsigned long _ppr; // Pulsos Por Rotação
    float _rpm;
    // Variáveis de tempo para o cálculo
    unsigned long _tempoAnterior;
    static const int _Ts_Encoder_ms; // 500ms para cada amostragem
    // Variável estática para ser acessada pela ISR
    static volatile uint32_t _pulsos;
    // A função da ISR em si (será chamada pelo hardware)
    static IRAM_ATTR void _contarPulsosISR();
};
#endif // ENCODER_H