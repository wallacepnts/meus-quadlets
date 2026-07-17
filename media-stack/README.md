# Media Stack — Podman Quadlet (rootless)

Deploy de nove serviços [LinuxServer.io](https://docs.linuxserver.io/) +
[Gluetun](https://github.com/qdm12/gluetun) + [Seerr](https://docs.seerr.dev)
via Podman Quadlet, todos enxergando a mesma raiz de mídia/downloads que
o [Jellyfin](../jellyfin/):

| Serviço | Papel | Porta |
| --- | --- | --- |
| [Prowlarr](https://prowlarr.com) | Gerenciador de indexers, alimenta os três abaixo | `9696` |
| [Sonarr](https://sonarr.tv) | Automação de séries | `8989` |
| [Radarr](https://radarr.video) | Automação de filmes | `7878` |
| [Lidarr](https://lidarr.audio) | Automação de música | `8686` |
| [Bazarr](https://www.bazarr.media) | Legendas automáticas pro Sonarr/Radarr | `6767` |
| [Seerr](https://docs.seerr.dev) | Pedidos de filme/série, integra com Jellyfin+Sonarr+Radarr | `5055` |
| [Gluetun](https://github.com/qdm12/gluetun) | Túnel VPN — só o Deluge passa por ele | — (sem UI própria) |
| [Deluge](https://deluge-torrent.org) | Cliente torrent, todo o tráfego via Gluetun | `8112` |
| [SABnzbd](https://sabnzbd.org) | Cliente usenet (sem VPN — ver por quê abaixo) | `8081` (a `8080` já é do [tsdproxy](../tsdproxy/) neste repo) |

**Sobre o Seerr**: é a continuação unificada do Overseerr (só Plex,
arquivado em 2024) e do Jellyseerr (fork da comunidade pra
Jellyfin/Emby) — os dois times se juntaram nesse projeto novo, que
suporta Plex/Jellyfin/Emby no mesmo código. Como usamos Jellyfin aqui,
Seerr é a escolha certa pra instalação nova — nem Overseerr nem
Jellyseerr fariam sentido hoje.

## Por que uma raiz de mídia só, compartilhada por todo mundo

Sonarr/Radarr/Lidarr **movem** arquivo de `downloads/` pra dentro de
`media/` quando terminam de importar — se `downloads/` e `media/`
estiverem em filesystems/mounts diferentes (um path pro Deluge, outro
pro Sonarr, outro pro Jellyfin), essa "movida" vira cópia + delete: mais
lento, usa I/O e espaço em disco à toa, e existe uma janela onde o
arquivo já não está mais em `downloads/` nem terminou de aparecer em
`media/`. Com todos os serviços montando a **mesma** raiz como `/data`,
a mesma movida é instantânea (hardlink/rename atômico, mesmo
filesystem).

Estrutura de pastas dentro da raiz escolhida (criar depois do primeiro
start, pela UI de cada app ou manualmente):

```
<sua raiz>/
├── media/
│   ├── movies/
│   ├── tv/
│   └── music/
└── downloads/
    ├── torrents/   # categoria/pasta de destino do Deluge
    └── usenet/      # pasta de destino do SABnzbd
```

**Path único, decidido uma vez, vale pra todos os oito + o Jellyfin** —
via uma variável `MEDIA_DATA_DIR` (não um path fixo tipo `%h/data`; ver
Instalação pra como isso é resolvido). Se sua mídia já mora em outro
disco/mount, aponte a variável direto pra lá, sem symlink nem cópia.

## Arquitetura

Nove containers, rede bridge padrão — exceto o Deluge, que entra na
stack de rede do Gluetun (`Network=container:gluetun`, ver seção VPN
abaixo) em vez de ter a própria. Nenhum `.network` dedicado — eles
conversam entre si via HTTP configurado manualmente depois de subir, não
via rede Podman compartilhada. `PUID`/`PGID`/`TZ` num único env file
(`media-stack.env`), reaproveitado pelos LinuxServer.io (exceto Gluetun,
que tem o próprio `gluetun.env` — credenciais de VPN não deveriam se
misturar com o resto) — ver
[README raiz, regra sobre UserNS vs PUID/PGID](../README.md) pro porquê
dessas imagens usarem esse mecanismo em vez do `UserNS=keep-id`. O Seerr
**não** é LinuxServer.io (roda fixo como uid 1000, sem o mecanismo de
usermod interno) — usa `UserNS=keep-id`, igual o Jellyfin, não o env
file compartilhado (`PUID`/`PGID` de lá são ignorados por ele, inofensivo,
mas não fazem nada).

`Prowlarr`, `Seerr` e `Gluetun` não montam `/data` — Prowlarr só
gerencia indexers e fala com os outros via API, Seerr só faz pedido
(fala com Sonarr/Radarr/Jellyfin via API, não toca em arquivo de mídia),
Gluetun é só o túnel de rede.

## Arquivos

```
quadlet/
├── prowlarr.container
├── sonarr.container
├── radarr.container
├── lidarr.container
├── bazarr.container
├── seerr.container
├── gluetun.container
├── deluge.container
└── sabnzbd.container
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando
- Uma conta de VPN com suporte a WireGuard ou OpenVPN, se for usar o
  Gluetun (ver [lista de provedores suportados](https://github.com/qdm12/gluetun-wiki/tree/main/setup/providers))

## Instalação do zero

```bash
# 1. Copiar as units
mkdir -p ~/.config/containers/systemd
cp quadlet/*.container ~/.config/containers/systemd/

# 2. Raiz de mídia — a ÚNICA decisão de path desta stack inteira (e do
#    Jellyfin), via uma variável de ambiente do systemd (não um
#    EnvironmentFile= comum — essa precisa existir no ambiente do
#    *manager* pra ser expandida dentro de Volume=; ver detalhes na
#    regra correspondente do README raiz).
mkdir -p ~/.config/environment.d
cat > ~/.config/environment.d/media-stack.conf <<EOF
MEDIA_DATA_DIR=$HOME/data
EOF
mkdir -p "$HOME/data"
# Se a mídia já mora em outro disco/mount, usar o path real ali em cima
# em vez de $HOME/data — nada de symlink, a variável já resolve isso.

# 3. Diretórios de config — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/media-stack/{prowlarr,sonarr,radarr,lidarr,bazarr,seerr,deluge,sabnzbd}/config

# 4. Env compartilhado — PUID/PGID do usuário que roda o Podman (mesmo
#    dono de MEDIA_DATA_DIR, senão os apps não conseguem escrever nela)
mkdir -p ~/.config/containers/env
cat > ~/.config/containers/env/media-stack.env <<EOF
PUID=$(id -u)
PGID=$(id -g)
TZ=America/Sao_Paulo
EOF

# 5. Env do Gluetun — provedor de VPN, ver a doc do provedor específico
#    (link acima) pras variáveis exatas. Exemplo genérico WireGuard:
cat > ~/.config/containers/env/gluetun.env <<EOF
VPN_SERVICE_PROVIDER=trocar_pelo_seu
VPN_TYPE=wireguard
WIREGUARD_PRIVATE_KEY=trocar_pela_sua_chave
WIREGUARD_ADDRESSES=trocar_pelo_seu_ip_interno
SERVER_COUNTRIES=trocar_pelo_pais_desejado
EOF
chmod 600 ~/.config/containers/env/gluetun.env

# 6. Aplicar a env.d nova (precisa de daemon-reload, não só reiniciar
#    o serviço — é o systemd --user que precisa reler o ambiente)
systemctl --user daemon-reload

# 7. Subir — Gluetun primeiro por causa da dependência do Deluge
#    (Requires=/After= já cuidam disso automaticamente)
systemctl --user start prowlarr sonarr radarr lidarr bazarr seerr gluetun deluge sabnzbd
```

Acessar cada um via [tsdproxy](../tsdproxy/) (tailnet, ex.:
`https://sonarr.<seu-tailnet>.ts.net`) ou local
(`http://localhost:<porta>`, ver tabela acima).

## Ligando os serviços entre si (depois do primeiro acesso)

Nenhum deles se descobre sozinho — configuração manual, uma vez, pela UI
de cada um:

1. **Deluge**: trocar a senha padrão (Preferências → Interface). Pasta
   de download: `/data/downloads/torrents`.
2. **SABnzbd**: assistente inicial pede o provedor usenet (servidor,
   usuário, senha). Pasta de download completo:
   `/data/downloads/usenet`.
3. **Sonarr/Radarr/Lidarr** — em cada um, Settings → Download Clients →
   adicionar Deluge (`localhost:8112`) e/ou SABnzbd (`localhost:8081`,
   nota: porta interna do container continua 8080, mas Sonarr/Radarr
   rodam no host, então usam a porta publicada `8081`). Settings → Media
   Management → Root Folder: `/data/media/tv` (Sonarr),
   `/data/media/movies` (Radarr), `/data/media/music` (Lidarr).
4. **Prowlarr** — Settings → Apps → adicionar Sonarr/Radarr/Lidarr (cada
   um pede a API key deles, em Settings → General de cada app). Depois,
   Indexers → adicionar os trackers/indexers desejados — o Prowlarr
   empurra pra todos os apps conectados sozinho.
5. **Bazarr** — Settings → Sonarr/Radarr, mesma lógica (URL local +
   API key), pra ele enxergar a mesma biblioteca e saber onde gravar
   legenda.
6. **Jellyfin** (ver [README próprio](../jellyfin/)) — biblioteca
   apontando pra `/data/media/movies`, `/data/media/tv` etc. Fazer
   **antes** do Seerr (próximo passo), que depende do Jellyfin já ter
   pelo menos uma biblioteca configurada.
7. **Seerr** — assistente inicial pede login: com conta do Jellyfin
   (`localhost:8096`) ou local. Depois, Settings → Services → adicionar
   Sonarr (`localhost:8989`) e Radarr (`localhost:7878`) com as API
   keys deles — é assim que um pedido aprovado no Seerr vira uma busca
   automática no Sonarr/Radarr.

## VPN no Deluge, via Gluetun

Só o **Deluge** passa pelo Gluetun — Sonarr/Radarr/Lidarr/Prowlarr/Bazarr
continuam na rede normal (não fazem P2P, não precisam). SABnzbd também
fica de fora de propósito: usenet é conexão direta e criptografada
(SSL) com o provedor, sem broadcast de IP pra outros peers como torrent
— o risco que a VPN mitiga no torrent praticamente não existe ali.

`Network=container:gluetun` no `deluge.container` faz o Deluge
compartilhar a stack de rede inteira do Gluetun — todo o tráfego dele
(torrent e o próprio painel web) sai pelo túnel. Consequência prática:
**se o Gluetun cair, o Deluge cai junto** (não tem rede própria pra
cair de volta) — na prática já funciona como um kill switch: sem VPN,
sem Deluge, sem vazamento de IP.

**Por que `PodmanArgs=--privileged` no Gluetun** — testado na prática
neste repositório: só `AddCapability=NET_ADMIN` (sem privileged) barra
no setup do firewall interno do próprio Gluetun, com erro de
`iptables`/`conntrack` — rootless não consegue mexer no netfilter real
do host mesmo com a capability concedida agora, só dentro do próprio
namespace remapeado. Com `--privileged` (ainda confinado ao user
namespace rootless — **não** é root real do host, diferente de rootful
Podman/Docker) o firewall interno sobe normal. Se preferir não usar
`--privileged` de jeito nenhum, dá pra desligar o firewall interno do
Gluetun (`FIREWALL=off` no `gluetun.env`) — funciona sem
`--privileged`, mas perde o kill switch próprio dele (ainda sobra o
"kill switch de fato" do `Network=container:` descrito acima, então o
risco residual é menor do que parece).

## Auto-update

Nenhum dos nove tem `AutoUpdate=` — tags explícitas (Gluetun inclusive,
apesar de estar em `:latest` aqui por enquanto — trocar pra uma tag
pinada é pendência), bump manual (regra 9 do README raiz). Os apps
LinuxServer.io e o Seerr guardam banco (SQLite, a maioria) com estado de
biblioteca/histórico/configuração de download em `/config` — mesma
cautela do [baikal](../baikal/)/[gitea](../gitea/): healthcheck confere
só se o servidor HTTP responde, não se uma migração de schema rodou
certo numa troca de versão.

## Backup & Recuperação

```bash
systemctl --user stop prowlarr sonarr radarr lidarr bazarr seerr deluge sabnzbd gluetun
tar -czf media-stack-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes media-stack
systemctl --user start prowlarr sonarr radarr lidarr bazarr seerr gluetun deluge sabnzbd
```

Só as pastas `config/` de cada serviço (API keys, configuração, estado
de download/indexer) — a mídia em si e os downloads brutos ficam fora,
mesmo raciocínio do Jellyfin. `~/.config/containers/env/gluetun.env`
(credenciais de VPN) também precisa de backup separado — sem ele, só
recriar do zero com o provedor.

## Considerações de segurança — não implementadas aqui

- **Portas de indexer/download client expostas na tailnet via tsdproxy**
  — como todo resto deste repositório, só alcançável de dentro da
  tailnet, não da internet pública.

## Comandos úteis

```bash
systemctl --user status prowlarr sonarr radarr lidarr bazarr seerr gluetun deluge sabnzbd
podman logs -f sonarr   # trocar pelo serviço que quiser
podman exec gluetun wget -qO- https://ipinfo.io/ip   # confirma que o IP saindo é o da VPN, não o do host
```

## Créditos

Deploy Quadlet baseado nas imagens [LinuxServer.io](https://github.com/linuxserver)
de [Prowlarr](https://github.com/Prowlarr/Prowlarr) (GPL-3.0),
[Sonarr](https://github.com/Sonarr/Sonarr) (GPL-3.0),
[Radarr](https://github.com/Radarr/Radarr) (GPL-3.0),
[Lidarr](https://github.com/Lidarr/Lidarr) (GPL-3.0),
[Bazarr](https://github.com/morpheus65535/bazarr) (GPL-3.0),
[Deluge](https://github.com/deluge-torrent/deluge) (GPL-3.0) e
[SABnzbd](https://github.com/sabnzbd/sabnzbd) (GPL-2.0). Pedidos de
mídia via [Seerr](https://github.com/seerr-team/seerr) (MIT), sucessor
unificado do Overseerr/Jellyseerr. Túnel VPN via
[Gluetun](https://github.com/qdm12/gluetun), de
[qdm12](https://github.com/qdm12) (MIT).
