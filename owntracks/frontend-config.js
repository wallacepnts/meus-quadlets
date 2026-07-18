// Config default (api.baseUrl usa o próprio host/protocolo — o nginx
// deste container já reverse-proxy /api/ e /ws/ pro owntracks-recorder,
// então não precisa apontar pra outro lugar). Ver opções em
// https://github.com/owntracks/frontend/blob/master/docs/config.md
window.owntracks = window.owntracks || {};
window.owntracks.config = {};
