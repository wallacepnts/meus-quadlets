# OwnTracks — Podman Quadlet (rootless)

Deploy do [OwnTracks Recorder](https://owntracks.org/booklet/clients/recorder/)
(backend de rastreamento de localização self-hosted, recebe posições dos
apps oficiais OwnTracks pro Android/iOS) + [Mosquitto](https://mosquitto.org)
(broker MQTT) + [OwnTracks Frontend](https://github.com/owntracks/frontend)
(interface web Vue.js mais completa que o viewer embutido no recorder)
via Podman Quadlet, migrado do
[`docker-compose-mqtt.yml`](https://github.com/owntracks/docker-recorder/blob/master/docker-compose-mqtt.yml)
oficial.

## Arquitetura

Três containers na rede `owntracks-net.network`:

- `mosquitto` — broker MQTT, expõe `1883` (protocolo nativo MQTT, é nele
  que os apps do celular publicam a localização) e `9001` (mesmo broker
  via WebSockets, pra clientes MQTT baseados em browser/JS — o app
  oficial do celular usa a `1883`, não essa)
- `owntracks-recorder` — assina `owntracks/#` no broker, grava cada
  posição recebida e expõe `8083` (interface web com mapa/histórico +
  API HTTP)
- `owntracks-frontend` — SPA Vue.js separada, expõe `80` (mapeado pra
  `8087` no host). nginx interno da imagem faz reverse-proxy de
  `/api/`/`/ws/` pro `owntracks-recorder` (via `SERVER_HOST`/`SERVER_PORT`)
  e serve os assets estáticos — não fala com o Mosquitto, só com o
  recorder. Só sobe depois que o recorder está de pé
  (`Requires=`/`After=`).

O viewer básico embutido no recorder (`owntracks.<seu-tailnet>.ts.net`)
e o frontend Vue.js (`owntracks-ui.<seu-tailnet>.ts.net`) convivem — os
dois leem a mesma API/dados, o frontend só tem mais recursos (mapa de
calor, filtros, etc.).

**Diferente do
[`docker-compose-mqtt.yml`](https://github.com/owntracks/docker-recorder/blob/master/docker-compose-mqtt.yml)
oficial**, que sobe o Mosquitto com `mosquitto -c /mosquitto-no-auth.conf`
(qualquer um na rede publica/assina sem autenticação — só serve pra
testar o recorder sozinho, o próprio comentário do compose já avisa
disso). Aqui o Mosquitto sobe com `allow_anonymous false` +
`password_file` desde o primeiro start — o mesmo usuário/senha MQTT é
usado tanto pelo `owntracks-recorder` quanto pelos apps do celular (ver
seção "Configurando o app" abaixo).

**Testado na prática: o `ot-recorder` não tolera o broker indisponível
no start** — sai com `Connection refused` em vez de esperar/retentar
sozinho, por isso `owntracks-recorder` só sobe depois que `mosquitto`
reporta `healthy` (`Requires=`/`After=`, mesmo padrão do
[linkwarden](../linkwarden/)/[any-sync-bundle](../any-sync-bundle/));
`Restart=always` cobre o caso do Mosquitto ainda não estar pronto na
primeira tentativa mesmo assim.

## Arquivos

```
quadlet/
├── owntracks-net.network        # rede dedicada
├── mosquitto.container          # broker MQTT
├── owntracks-recorder.container # aplicação (backend + viewer básico)
└── owntracks-frontend.container # UI Vue.js separada

mosquitto.conf                   # config do broker (auth habilitada)
frontend-config.js               # config do frontend (padrão vazio)
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando
- `openssl` (pra gerar a senha MQTT)

## Instalação do zero

```bash
# 1. Copiar as units
mkdir -p ~/.config/containers/systemd/owntracks
cp quadlet/*.container quadlet/*.network ~/.config/containers/systemd/owntracks/

# 2. Diretórios — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/owntracks/{mosquitto/config,mosquitto/data,store,config}
cp mosquitto.conf ~/.config/containers/volumes/owntracks/mosquitto/config/
cp frontend-config.js ~/.config/containers/volumes/owntracks/frontend-config.js

# 3. Senha MQTT — gerada uma vez, usada pelo app do celular pra
#    autenticar no broker. Os dois segredos abaixo (arquivo passwd do
#    Mosquitto e OTR_PASS do recorder) embutem a MESMA senha.
mkdir -p ~/.config/containers/secrets/owntracks
MQTT_PW=$(openssl rand -base64 24 | tr -d '\n')

# 3a. passwd do Mosquitto — mosquitto_passwd gera o hash, viramos secret
#     em vez de deixar como arquivo solto no volume (regra 2 do README
#     raiz). Secret montado como arquivo já vem 0444 (mundo-legível) por
#     padrão do Podman — funciona mesmo o mosquitto rodando
#     internamente como usuário não-root "mosquitto".
podman run --rm --entrypoint mosquitto_passwd \
  -v ~/.config/containers/secrets/owntracks:/secrets:Z \
  docker.io/library/eclipse-mosquitto:2.1.2-alpine \
  -b -c /secrets/mosquitto-passwd owntracks "$MQTT_PW"
podman secret create owntracks-mosquitto-passwd ~/.config/containers/secrets/owntracks/mosquitto-passwd

# 3b. OTR_PASS do recorder — mesma senha, crua (não hash), pro cliente
#     MQTT do próprio recorder autenticar no broker
echo -n "$MQTT_PW" > ~/.config/containers/secrets/owntracks/mqtt-password.txt
chmod 600 ~/.config/containers/secrets/owntracks/mqtt-password.txt
podman secret create owntracks-mqtt-password ~/.config/containers/secrets/owntracks/mqtt-password.txt
echo "Senha MQTT (configurar no app do celular): $MQTT_PW"

# 4. Env não-secreto — copiar o exemplo (padrão já bate com o usuário
#    criado acima; só editar se quiser um nome de usuário diferente de
#    "owntracks", refazendo o passo 3 com esse nome)
mkdir -p ~/.config/containers/env
cp .env.example ~/.config/containers/env/owntracks-recorder.env

# 5. Subir (mosquitto sobe primeiro via Requires=; o frontend sobe
#    depois do recorder, mesma lógica)
systemctl --user daemon-reload
systemctl --user start owntracks-frontend
```

Viewer básico embutido no recorder via [tsdproxy](../tsdproxy/)
(tailnet) em `https://owntracks.<seu-tailnet>.ts.net`, ou local em
`http://localhost:8086`. UI Vue.js mais completa em
`https://owntracks-ui.<seu-tailnet>.ts.net`, ou local em
`http://localhost:8087` — mapa com o histórico de posições recebidas
(vazio até o primeiro app do celular publicar algo).

**Sem autenticação própria em nenhuma das duas interfaces web** — mesmo
modelo de confiança já usado pelo [WUD](../wud/)/[Homepage](../homepage/)
neste repositório: protegido só por estar na tailnet, não por login.

## Configurando o app OwnTracks no celular

No app (Android/iOS), modo de reporte **MQTT** (não HTTP):

| Campo | Valor |
| --- | --- |
| Host | hostname do **próprio host** na tailnet (`<nome-deste-host>.<seu-tailnet>.ts.net`, ver `tailscale status` nele) ou IP local — **não** `owntracks.<seu-tailnet>.ts.net` (ver observação abaixo) |
| Port | `1883` |
| TLS | desligado (sem certificado configurado aqui — ver observação abaixo) |
| Usuário | `owntracks` (ou o que tiver sido usado no passo 3 da instalação) |
| Senha | a senha impressa no passo 3 |
| ClientID/DeviceID | um por dispositivo, livre |
| Protocol level (session) | `4` (MQTT 3.1.1) |
| URL | em branco |
| Encryption key | em branco |

**Por que o hostname do host, não `owntracks.<seu-tailnet>.ts.net`**:
testado na prática — proxy TCP puro (`tsdproxy.port.*`, mesmo mecanismo
do [any-sync-bundle](../any-sync-bundle/)) trava permanentemente em
"Starting"/`NeedsLogin` no tsdproxy 2.3.4, nunca chega a `Running` (o
any-sync-bundle mostra o mesmo sintoma nos logs — health check falhando
em loop — não é specific deste app). `mosquitto.container` não declara
labels do tsdproxy por causa disso. Como `PublishPort=1883:1883` já
expõe a porta em **todas** as interfaces do host — incluindo a própria
interface da tailnet, não só localhost —, o hostname do host funciona
direto, sem precisar do tsdproxy nesse caminho. A interface web
(`owntracks.<seu-tailnet>.ts.net`) continua funcionando normal, é só a
porta MQTT que não passa pelo tsdproxy.

**URL em branco**: esse campo é do modo **HTTP** (endpoint tipo
`https://.../pub`), não do MQTT — o app mostra os dois grupos de campos
na mesma tela independente do modo escolhido. Sem efeito aqui, já que o
modo é MQTT.

**Encryption key em branco**: criptografa o payload da localização antes
de publicar no broker — pensado pra quando o broker é compartilhado ou
público e você não confia em quem mais tem acesso a ele. Como este
Mosquitto só é alcançável de dentro da tailnet e é de uso pessoal, não
agrega segurança real, só complexidade (o recorder precisaria carregar
a mesma chave via `ocat --load=keys` pra conseguir decodificar as
posições).

**Protocol level `4`, não `3`/`5`**: é o "protocol level" do pacote
CONNECT do MQTT — `3` = MQTT 3.1, `4` = MQTT 3.1.1, `5` = MQTT 5.0. O
Mosquitto 2.1.2 aceita os três, mas `4`/3.1.1 é o mais testado e
compatível, o que o próprio `ot-recorder` usa — MQTT 5.0 traz recursos
que nem o recorder nem a maioria dos clientes exploram, sem ganho
prático aqui.

**Por que `1883`, não `8883`**: `8883` é a porta padrão de MQTT **com
TLS** (MQTTS) — como este deploy não configura certificado nenhum (ver
observação abaixo), não existe listener TLS pra atender ali. `1883` é a
porta certa pro MQTT nativo em texto puro, que é o que está de pé aqui.

**Sem TLS**: o tráfego MQTT sai em texto puro (só a senha, que trafega
com autenticação básica do protocolo, sem estar por trás de HTTPS) —
aceitável aqui porque, como todo resto deste repositório, só é alcançável
de dentro da tailnet, nunca da internet pública. Adicionar TLS
depois é possível (`listener` extra em `mosquitto.conf` com
`certfile`/`keyfile`/`cafile`, ver o
[`docker-compose-ssl.yml`](https://github.com/owntracks/docker-recorder/blob/master/docker-compose-ssl.yml)
oficial), mas não é o padrão deste deploy.

## WebSockets (porta `9001`)

Além da `1883` (MQTT nativo, usado pelo app do celular), o Mosquitto
também escuta em `9001` com `protocol websockets` — útil só se algum dia
quiser conectar um cliente MQTT baseado em browser/JS (ex.: um
dashboard próprio) direto no broker. Mesma autenticação
(usuário/senha do passo 3) vale pros dois listeners, já que
`mosquitto.conf` não usa `per_listener_settings`. Nenhum dos dois
containers deste deploy (recorder ou algum viewer) usa esse listener —
ele fica disponível, mas ocioso, até que algo o use.

**No app do celular, não ativar/usar WebSockets — deixar no MQTT nativo
(`1883`, ver tabela acima).** WebSockets existe pra contornar ambientes
onde só dá pra abrir socket via HTTP (principalmente browsers/JS, que
não têm acesso a socket TCP cru). O app oficial do OwnTracks
(Android/iOS) implementa MQTT nativamente, sem essa limitação — usar
WebSockets ali só adicionaria overhead, sem ganho nenhum.

## Auto-update

Sem `AutoUpdate=` — tags explícitas (`1.0.1` no recorder, `2.15.3` no
frontend, `2.1.2-alpine` no mosquitto), bump manual (regra 9 do README
raiz). As três imagens também publicam variantes com sufixo de build
(`1.0.1-43`, `2.1.2-alpine` vs. bare `2.1.2`) que confundiriam o parser
semver do WUD — `wud.watch=true` está no `owntracks-recorder` e no
`owntracks-frontend` (os dois apps voltados ao usuário), com
`wud.tag.include` restringindo a candidatos `X.Y.Z` puro; o `mosquitto`
fica de fora (dependência interna, mesmo padrão já aplicado a
bancos/caches no resto do repositório).

## Backup & Recuperação

```bash
systemctl --user stop owntracks-frontend owntracks-recorder mosquitto
tar -czf owntracks-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes owntracks
systemctl --user start owntracks-frontend
```

`store/` é o histórico de localização de verdade (LMDB) — o que importa
de verdade aqui. `mosquitto/data/` guarda só o persistence file do
broker (retained messages, se algum), perda é inconveniente, não
destrutiva. `frontend-config.js` só importa se você tiver customizado
algo além do padrão vazio. `~/.config/containers/secrets/owntracks/`
(senha crua + hash do passwd do Mosquitto) também precisa de backup
separado — sem ele, os celulares perdem acesso ao broker até
reconfigurar a senha.

## Comandos úteis

```bash
systemctl --user status owntracks-frontend owntracks-recorder mosquitto
podman logs -f owntracks-recorder
podman logs -f owntracks-frontend
podman logs -f mosquitto
curl -s http://127.0.0.1:8086/api/0/list   # usuários/devices já registrados
```

## Créditos

Deploy Quadlet baseado no [OwnTracks Recorder](https://github.com/owntracks/recorder)
(GPL-2.0), de [Jan-Piet Mens](https://github.com/jpmens), e no
[docker-recorder](https://github.com/owntracks/docker-recorder) oficial
(imagem + `docker-compose-mqtt.yml` de referência). Interface web via
[OwnTracks Frontend](https://github.com/owntracks/frontend) (MIT).
Broker MQTT via [Eclipse Mosquitto](https://github.com/eclipse-mosquitto/mosquitto)
(EPL-2.0/EDL-1.0).
