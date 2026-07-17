# Home Assistant — Podman Quadlet (rootless)

Deploy do [Home Assistant Container](https://www.home-assistant.io/installation/alternative/)
via Podman Quadlet.

## Decisões deste deploy

A instalação oficial recomenda `network_mode: host` + `privileged: true`
+ acesso ao D-Bus do host, pra descoberta automática de dispositivos
(mDNS/SSDP — Hue, Chromecast, HomeKit...) e passthrough de hardware
(dongle Zigbee/Z-Wave via `/dev/ttyUSB0`). Nenhum dos dois foi usado
aqui, de propósito:

- **Rede bridge normal** (`PublishPort=8123:8123`), não `host`. Perde a
  descoberta automática por mDNS/SSDP — dispositivos precisam ser
  adicionados manualmente pela UI (Configurações → Dispositivos e
  serviços). Em troca, mantém o mesmo isolamento de rede que todo resto
  deste repositório tem; `host` colocaria a HA na mesma rede que o host
  literalmente, fora do padrão usado aqui.
- **Sem dispositivo USB passado** — sem dongle Zigbee/Z-Wave neste setup
  por enquanto. Se algum dia entrar um, ver seção própria abaixo pra
  adicionar via `AddDevice=`.
- **Sem D-Bus/Bluetooth** — mesma lógica; integração via Bluetooth do
  host não funciona sem isso, mas não é necessário pro uso atual.

Consequência visível no log, inofensiva: `Cannot watch for dhcp
packets: Operation not permitted` — o watcher de DHCP (mais um
mecanismo de descoberta automática, via pacotes DHCP passivos) exige
`CAP_NET_RAW`, que rede bridge sem privileged não dá. Não impede a HA
de funcionar, só mais uma frente de descoberta automática que fica sem
efeito — coerente com a decisão acima.

Se algum desses três entrar no futuro (mDNS, USB, Bluetooth), a solução
mais simples costuma ser `network_mode: host` mesmo — tentar replicar
descoberta mDNS através de bridge é frágil (precisaria de proxy mDNS
tipo `avahi`/[repeater](https://github.com/dmitrykim/mdns-repeater), sem
suporte oficial da HA). Reavaliar então.

## Arquitetura

Container único, imagem oficial (Debian + Python). Um volume só
(`/config`) guarda toda a configuração, automações, histórico de estado
(banco SQLite embutido por padrão) e logs.

## Arquivos

```
quadlet/
└── home-assistant.container   # unit principal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero

```bash
# 1. Copiar a unit
mkdir -p ~/.config/containers/systemd
cp quadlet/home-assistant.container ~/.config/containers/systemd/

# 2. Diretório de dados — bind mount exige que já exista antes do start
mkdir -p ~/.config/containers/volumes/home-assistant/config

# 3. Env — copiar o exemplo
mkdir -p ~/.config/containers/env
cp .env.example ~/.config/containers/env/home-assistant.env

# 4. Subir
systemctl --user daemon-reload
systemctl --user start home-assistant
```

Acessar via [tsdproxy](../tsdproxy/) (tailnet) em
`https://home-assistant.<seu-tailnet>.ts.net`, ou local em
`http://localhost:8123` — a raiz redireciona pro assistente de
instalação na primeira vez (criar conta, nome do local, unidades etc.).

**Trusted proxies — precisa mesmo, não é "se acontecer".** Acessando via
tsdproxy (reverse proxy), a HA recusa a conexão com `400: Bad Request` e
loga `A request from a reverse proxy was received from 169.254.1.2, but
your HTTP integration is not set-up for reverse proxies`. `169.254.1.2`
é o gateway interno do Podman rootless (via pasta — mesmo endereço por
trás do `host.containers.internal`, ver [zerobyte](../zerobyte/) pra
outro caso onde ele aparece), é por ele que o tráfego do tsdproxy chega.
Adicionar em
`~/.config/containers/volumes/home-assistant/config/configuration.yaml`
**antes** de tentar acessar pela tailnet, depois `systemctl --user
restart home-assistant`:

```yaml
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 169.254.1.2
```

## Adicionando um dispositivo USB (Zigbee/Z-Wave) depois

```ini
AddDevice=/dev/ttyUSB0
```

Conferir o path real com `ls -la /dev/serial/by-id/` no host (mais
estável que `/dev/ttyUSB0`, que pode mudar de número entre boots) e
usar esse no lugar. Sem `--privileged`/host network, isso já deve
bastar pro dongle aparecer dentro do container — testar antes de reativar
`network_mode: host`.

## Auto-update

Sem `AutoUpdate=` — tag explícita (`2026.7.2`), bump manual (regra 9 do
README raiz). Releases da HA são mensais e às vezes trazem *breaking
changes* documentadas nas release notes (integração descontinuada,
mudança de config) — revisão manual antes de trocar de versão, mesma
cautela do [linkwarden](../linkwarden/).

## Backup & Recuperação

```bash
systemctl --user stop home-assistant
tar -czf home-assistant-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes home-assistant
systemctl --user start home-assistant
```

A própria HA também tem backup embutido pela UI (Configurações →
Sistema → Backups) — mais prático pro dia a dia (não exige parar o
container), o tar acima é o equivalente "a frio" caso a UI não seja
suficiente ou o container não suba mais.

## Comandos úteis

```bash
systemctl --user status home-assistant
podman logs -f home-assistant
```

## Créditos

Deploy Quadlet baseado no [Home Assistant](https://github.com/home-assistant/core).
Licença original: Apache-2.0.
