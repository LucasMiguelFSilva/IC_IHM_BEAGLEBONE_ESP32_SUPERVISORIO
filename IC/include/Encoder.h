#ifndef ENCODER_H
#define ENCODER_H

#include <Arduino.h>

class Encoder {
public:
    Encoder(int pinA, unsigned long pulsosPorRotacao);
    void begin();
    void loop();
    float getRPM();

private:
    int _pinA;
    unsigned long _ppr;
    float _rpm;

    unsigned long _tempoAnterior; 
    
    // CORREÇÃO: Removido o valor daqui. Agora é só uma declaração.
    static constexpr int _Ts_Encoder_ms = 500; 

    static volatile uint32_t _pulsos;
    static IRAM_ATTR void _contarPulsosISR();
};

#endif // ENCODER_H