// api.baseUrl não é setado de propósito: o nginx deste container já
// reverse-proxy /api/ e /ws/ pro owntracks-recorder, então o padrão
// (protocolo/host atual) já resolve certo. Ver todas as opções em
// https://github.com/owntracks/frontend/blob/master/docs/config.md
window.owntracks = window.owntracks || {};
window.owntracks.config = {
  filters: {
    // Descarta pontos de GPS com precisão pior que 100m — sem isso,
    // outliers distorcem o cálculo de distância percorrida (a própria
    // doc recomenda ligar isso).
    minAccuracy: 100,
  },
  map: {
    // Não conecta dois pontos com mais de 1km de distância na mesma
    // linha — evita "teletransporte" visual no mapa quando há um salto
    // grande entre pontos (GPS ruim, celular desligado por um tempo).
    maxPointDistance: 1000,
  },
};
