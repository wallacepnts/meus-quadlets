# Media Stack — Podman Quadlet (rootless)

Deploy de [Jellyfin](https://jellyfin.org) + nove serviços
[LinuxServer.io](https://docs.linuxserver.io/)/[Seerr](https://docs.seerr.dev)
via Podman Quadlet, todos enxergando a mesma raiz de mídia/downloads.

| Serviço | Papel | Porta |
| --- | --- | --- |
| [Jellyfin](https://jellyfin.org) | Servidor de mídia | `8096` |
| [Prowlarr](https://prowlarr.com) | Gerenciador de indexers, alimenta os três abaixo | `9696` |
| [Sonarr](https://sonarr.tv) | Automação de séries | `8989` |
| [Radarr](https://radarr.video) | Automação de filmes | `7878` |
| [Lidarr](https://lidarr.audio) | Automação de música | `8686` |
| [Bazarr](https://www.bazarr.media) | Legendas automáticas pro Sonarr/Radarr | `6767` |
| [Seerr](https://docs.seerr.dev) | Pedidos de filme/série, integra com Jellyfin+Sonarr+Radarr | `5055` |
| [Deluge](https://deluge-torrent.org) | Cliente torrent | `8112` |
| [SABnzbd](https://sabnzbd.org) | Cliente usenet | `8081` (a `8080` já é do [tsdproxy](../tsdproxy/) neste repo) |

Um décimo serviço, o [Gluetun](https://github.com/qdm12/gluetun) (túnel
VPN pro Deluge), é **opcional** — ver seção própria abaixo.

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

**Path único, decidido uma vez, vale pra todos os dez** — via uma
variável `MEDIA_DATA_DIR` (não um path fixo tipo `%h/data`; ver
Instalação pra como isso é resolvido). Se sua mídia já mora em outro
disco/mount, aponte a variável direto pra lá, sem symlink nem cópia.

## Arquitetura

Rede bridge padrão, cada serviço com sua `PublishPort=`. Nenhum
`.network` dedicado — eles conversam entre si via HTTP configurado
manualmente depois de subir, não via rede Podman compartilhada.

Dois mecanismos diferentes pra mapear permissão de arquivo, dependendo
da imagem — ver [README raiz, regra sobre UserNS vs PUID/PGID](../README.md)
pro porquê dos dois não se misturarem:

- **LinuxServer.io** (Prowlarr/Sonarr/Radarr/Lidarr/Bazarr/Deluge/SABnzbd):
  `PUID`/`PGID`/`TZ` num único env file (`media-stack.env`), reaproveitado
  por todos eles — a imagem faz `usermod` internamente, exige rodar como
  root de verdade dentro do próprio namespace do container.
- **Jellyfin e Seerr** (não são LinuxServer.io — Jellyfin executa o
  binário direto, Seerr roda fixo como uid 1000/"node", nenhum dos dois
  tem esse mecanismo de usermod interno): `UserNS=keep-id`, que mapeia o
  container pro mesmo uid do usuário que roda o Podman. `PUID`/`PGID` do
  env file compartilhado são ignorados por eles quando presentes
  (inofensivo, mas não fazem nada).

`Prowlarr` e `Seerr` não montam `/data` — Prowlarr só gerencia indexers
e fala com os outros via API, Seerr só faz pedido (fala com
Sonarr/Radarr/Jellyfin via API, não toca em arquivo de mídia).

**Jellyfin em rede bridge, não `host`** — mesma lógica já aplicada ao
[Home Assistant](../home-assistant/): perde autodiscovery de clientes na
LAN (porta `7359/udp`, broadcast — não atravessa bridge/NAT direito),
mas mantém o isolamento de rede padrão deste repositório. Sem
autodiscovery, os clientes Jellyfin (apps de TV, mobile etc.) pedem o
endereço do servidor manualmente na primeira configuração — funciona
normal, só não aparece sozinho na lista.

## Arquivos

```
quadlet/
├── jellyfin.container
├── prowlarr.container
├── sonarr.container
├── radarr.container
├── lidarr.container
├── bazarr.container
├── seerr.container
├── deluge.container
├── sabnzbd.container
└── gluetun.container   # opcional — ver seção VPN abaixo
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero

```bash
# 1. Copiar as units (inclui gluetun.container; só importa se for usar
#    a seção de VPN abaixo — sem ativar, fica parado sem nenhum custo)
mkdir -p ~/.config/containers/systemd
cp quadlet/*.container ~/.config/containers/systemd/

# 2. Raiz de mídia — a ÚNICA decisão de path desta stack inteira, via uma
#    variável de ambiente do systemd (não um EnvironmentFile= comum —
#    essa precisa existir no ambiente do *manager* pra ser expandida
#    dentro de Volume=; ver detalhes na regra correspondente do README
#    raiz).
mkdir -p ~/.config/environment.d
cat > ~/.config/environment.d/media-stack.conf <<EOF
MEDIA_DATA_DIR=$HOME/data
EOF
mkdir -p "$HOME/data"
# Se a mídia já mora em outro disco/mount, usar o path real ali em cima
# em vez de $HOME/data — nada de symlink, a variável já resolve isso.

# 3. Diretórios de config — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/jellyfin/{config,cache}
mkdir -p ~/.config/containers/volumes/media-stack/{prowlarr,sonarr,radarr,lidarr,bazarr,seerr,deluge,sabnzbd}/config

# 4. Env compartilhado (LinuxServer.io) — PUID/PGID do usuário que roda
#    o Podman (mesmo dono de MEDIA_DATA_DIR, senão os apps não
#    conseguem escrever nela)
mkdir -p ~/.config/containers/env
cat > ~/.config/containers/env/media-stack.env <<EOF
PUID=$(id -u)
PGID=$(id -g)
TZ=America/Sao_Paulo
EOF

# 5. Aplicar a env.d nova (precisa de daemon-reload, não só reiniciar
#    o serviço — é o systemd --user que precisa reler o ambiente)
systemctl --user daemon-reload

# 6. Subir (sem o Gluetun — ver seção própria pra ativar VPN)
systemctl --user start jellyfin prowlarr sonarr radarr lidarr bazarr seerr deluge sabnzbd
```

Acessar cada um via [tsdproxy](../tsdproxy/) (tailnet, ex.:
`https://sonarr.<seu-tailnet>.ts.net`) ou local
(`http://localhost:<porta>`, ver tabela acima).

## Ligando os serviços entre si (depois do primeiro acesso)

Nenhum deles se descobre sozinho — configuração manual, uma vez, pela UI
de cada um:

1. **Jellyfin** — assistente inicial (idioma, conta admin, adicionar
   biblioteca apontando pro path montado em `/data`, ex.:
   `/data/media/movies`, `/data/media/tv`). Fazer **antes** do Seerr
   (passo 7), que depende do Jellyfin já ter pelo menos uma biblioteca
   configurada. Ver seção de transcodificação por hardware abaixo, se
   for habilitar.
2. **Deluge**: senha inicial é `deluge` — trocar em Preferências →
   Interface → Password assim que logar. Pasta de download:
   `/data/downloads/torrents`.
3. **SABnzbd**: assistente inicial pede o provedor usenet (servidor,
   usuário, senha). Pasta de download completo:
   `/data/downloads/usenet`. Acessando via tsdproxy, dá `External
   internet access denied` — o SABnzbd bloqueia por padrão qualquer
   acesso que não pareça vir da rede local, e o tráfego do tsdproxy
   chega pelo gateway interno do Podman (`169.254.1.2`, mesmo endereço
   por trás do `host.containers.internal` — ver [zerobyte](../zerobyte/)),
   que não bate. Corrigir subindo o `inet_exposure` — pela UI (Config →
   General → "External internet access", pra `Full web interface`, ou
   "- Only external access requires login" se quiser exigir senha só de
   fora) ou direto no arquivo, sem precisar abrir o navegador (nem
   variável de ambiente nem argumento de linha de comando funcionam
   aqui — testado na prática: `Exec=--inet_exposure 4` no `.container`
   quebra a inicialização, o script de init dessa imagem não repassa
   argumento extra pro `sabnzbd.py`, tenta executar `--inet_exposure`
   como se fosse um programa):

   ```bash
   systemctl --user stop sabnzbd
   podman unshare sed -i 's/^inet_exposure = 0/inet_exposure = 4/' \
     ~/.config/containers/volumes/media-stack/sabnzbd/config/sabnzbd.ini
   systemctl --user start sabnzbd
   ```

   Diferente do "Hostname verification failed" (outro mecanismo do
   SABnzbd, baseado em `host_whitelist` por nome, não IP) — esse aqui é
   o `inet_exposure`.
4. **Sonarr/Radarr/Lidarr** — em cada um, Settings → Download Clients →
   adicionar Deluge (`localhost:8112`) e/ou SABnzbd (`localhost:8081`,
   nota: porta interna do container continua 8080, mas Sonarr/Radarr
   rodam no host, então usam a porta publicada `8081`). Settings → Media
   Management → Root Folder: `/data/media/tv` (Sonarr),
   `/data/media/movies` (Radarr), `/data/media/music` (Lidarr).
5. **Prowlarr** — Settings → Apps → adicionar Sonarr/Radarr/Lidarr (cada
   um pede a API key deles, em Settings → General de cada app). Depois,
   Indexers → adicionar os trackers/indexers desejados — o Prowlarr
   empurra pra todos os apps conectados sozinho.
6. **Bazarr** — Settings → Sonarr/Radarr, mesma lógica (URL local +
   API key), pra ele enxergar a mesma biblioteca e saber onde gravar
   legenda.
7. **Seerr** — assistente inicial pede login: com conta do Jellyfin
   (`localhost:8096`) ou local. Depois, Settings → Services → adicionar
   Sonarr (`localhost:8989`) e Radarr (`localhost:7878`) com as API
   keys deles — é assim que um pedido aprovado no Seerr vira uma busca
   automática no Sonarr/Radarr.

## Transcodificação por hardware (Jellyfin)

Sem isso, transcodificação usa só CPU — funciona, mas não escala bem
pra vários streams simultâneos ou 4K. Adicionar no `jellyfin.container`
**antes** de subir (ou editar e `systemctl --user daemon-reload &&
systemctl --user restart jellyfin` depois):

### Intel/AMD (`/dev/dri`, VAAPI/QSV)

```ini
AddDevice=/dev/dri:/dev/dri
```

Em host com SELinux enforcing, também pode ser necessário:

```bash
sudo setsebool -P container_use_dri_devices 1
```

Depois, em Painel administrativo → Reprodução, selecionar VAAPI (AMD)
ou QSV (Intel) como aceleração de hardware.

### NVIDIA (NVENC/NVDEC) — mais trabalhoso

Precisa do [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
instalado no host primeiro (driver NVIDIA já funcionando é pré-requisito
implícito). Depois, gerar a especificação CDI — em rootless, no
namespace do próprio usuário:

```bash
mkdir -p ~/.config/cdi
nvidia-ctk cdi generate --output=$HOME/.config/cdi/nvidia.yaml
```

Em host com SELinux enforcing:

```bash
sudo setsebool -P container_use_devices 1
```

Adicionar no `jellyfin.container`:

```ini
AddDevice=nvidia.com/gpu=all
```

Depois, em Painel administrativo → Reprodução, selecionar NVIDIA NVENC.
A partir do NVIDIA Container Toolkit v1.18.0 existe um serviço
`nvidia-cdi-refresh` que mantém a especificação CDI atualizada sozinha
(driver atualizado, GPU trocada etc.) — sem ele, refazer o
`nvidia-ctk cdi generate` manualmente após qualquer mudança de driver.

## VPN opcional no Deluge, via Gluetun

Por padrão o Deluge sobe **sem VPN** — tráfego de torrent sai direto
pelo IP do host, mesma rede que os outros serviços. `gluetun.container`
já vem junto no repositório, parado até ser ativado; ativar depois não
exige reinstalar nada.

**Se for ativar**, o padrão recomendado é rotear só o Deluge (não o
resto — Sonarr/Radarr/Lidarr/Prowlarr/Bazarr não fazem P2P, não
precisam de VPN; SABnzbd também fica de fora de propósito, usenet é
conexão direta e criptografada com o provedor, sem broadcast de IP pra
peers como no torrent):

`gluetun.container` já vem pronto pra isso (portas do Deluge publicadas
nele, healthcheck, `--privileged` — ver justificativa abaixo). Só falta:

```bash
# 1. Credenciais do provedor de VPN (ver lista de provedores suportados:
#    https://github.com/qdm12/gluetun-wiki/tree/main/setup/providers)
cat > ~/.config/containers/env/gluetun.env <<EOF
VPN_SERVICE_PROVIDER=trocar_pelo_seu
VPN_TYPE=wireguard
WIREGUARD_PRIVATE_KEY=trocar_pela_sua_chave
WIREGUARD_ADDRESSES=trocar_pelo_seu_ip_interno
SERVER_COUNTRIES=trocar_pelo_pais_desejado
EOF
chmod 600 ~/.config/containers/env/gluetun.env

# 2. Editar deluge.container: trocar as três linhas de PublishPort= por
#    Network=container:gluetun, e adicionar em [Unit]:
#      After=gluetun.service
#      Requires=gluetun.service
#    (container que entra via "container:" não declara PublishPort=
#    próprio nem Network=<nome>.network — a porta já está publicada no
#    gluetun.container, é por isso que os labels tsdproxy.* de descoberta
#    também já estão lá, não no deluge.container)

systemctl --user daemon-reload
systemctl --user stop deluge
systemctl --user start gluetun deluge
```

`Network=container:gluetun` faz o Deluge compartilhar a stack de rede
inteira do Gluetun — todo o tráfego dele (torrent e o próprio painel
web) sai pelo túnel. Consequência prática: **se o Gluetun cair, o
Deluge cai junto** (não tem rede própria pra cair de volta) — na
prática já funciona como um kill switch: sem VPN, sem Deluge, sem
vazamento de IP.

**Por que `PodmanArgs=--privileged` no Gluetun** (já vem assim no
`gluetun.container` deste repo) — testado na prática: só
`AddCapability=NET_ADMIN` (sem privileged) barra no setup do firewall
interno do próprio Gluetun, com erro de `iptables`/`conntrack` —
rootless não consegue mexer no netfilter real do host mesmo com a
capability concedida, só dentro do próprio namespace remapeado. Com
`--privileged` (ainda confinado ao user namespace rootless — **não** é
root real do host, diferente de rootful Podman/Docker) o firewall
interno sobe normal. Se preferir não usar `--privileged` de jeito
nenhum, dá pra desligar o firewall interno do Gluetun (`FIREWALL=off`
no `gluetun.env`) — funciona sem `--privileged`, mas perde o kill
switch próprio dele (ainda sobra o "kill switch de fato" do
`Network=container:` descrito acima, então o risco residual é menor do
que parece).

Conferir que o IP saindo é o da VPN, não o do host:
```bash
podman exec gluetun wget -qO- https://ipinfo.io/ip
```

## Auto-update

Nenhum dos serviços tem `AutoUpdate=` — tags explícitas, bump manual
(regra 9 do README raiz; o `gluetun.container` deste repo é exceção
consciente, fica em `:latest` porque o próprio projeto não publica
releases versionadas de forma estável — reavaliar se isso mudar).
Jellyfin, os apps LinuxServer.io e o Seerr guardam banco (SQLite, a
maioria) com estado de biblioteca/histórico/configuração de download em
`/config` — mesma cautela do [baikal](../baikal/)/[gitea](../gitea/):
healthcheck confere só se o servidor HTTP responde, não se uma migração
de schema rodou certo numa troca de versão.

## Backup & Recuperação

```bash
systemctl --user stop jellyfin prowlarr sonarr radarr lidarr bazarr seerr deluge sabnzbd
tar -czf media-stack-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes jellyfin media-stack
systemctl --user start jellyfin prowlarr sonarr radarr lidarr bazarr seerr deluge sabnzbd
```

Só as pastas `config/`/`cache/` de cada serviço (API keys, configuração,
estado de download/indexer, biblioteca/histórico do Jellyfin) — a mídia
em si e os downloads brutos ficam fora, fora de
`~/.config/containers/volumes/`, gerenciados separadamente por quem
instalou. Se estiver usando o Gluetun,
`~/.config/containers/env/gluetun.env` (credenciais de VPN) também
precisa de backup separado — sem ele, só recriar do zero com o provedor.

## Considerações de segurança — não implementadas aqui

- **Portas de indexer/download client expostas na tailnet via tsdproxy**
  — como todo resto deste repositório, só alcançável de dentro da
  tailnet, não da internet pública.

## Comandos úteis

```bash
systemctl --user status jellyfin prowlarr sonarr radarr lidarr bazarr seerr deluge sabnzbd
podman logs -f sonarr   # trocar pelo serviço que quiser
```

## Créditos

Deploy Quadlet baseado no [Jellyfin](https://github.com/jellyfin/jellyfin)
(GPL-2.0) e nas imagens [LinuxServer.io](https://github.com/linuxserver)
de [Prowlarr](https://github.com/Prowlarr/Prowlarr) (GPL-3.0),
[Sonarr](https://github.com/Sonarr/Sonarr) (GPL-3.0),
[Radarr](https://github.com/Radarr/Radarr) (GPL-3.0),
[Lidarr](https://github.com/Lidarr/Lidarr) (GPL-3.0),
[Bazarr](https://github.com/morpheus65535/bazarr) (GPL-3.0),
[Deluge](https://github.com/deluge-torrent/deluge) (GPL-3.0) e
[SABnzbd](https://github.com/sabnzbd/sabnzbd) (GPL-2.0). Pedidos de
mídia via [Seerr](https://github.com/seerr-team/seerr) (MIT), sucessor
unificado do Overseerr/Jellyseerr. Túnel VPN opcional via
[Gluetun](https://github.com/qdm12/gluetun), de
[qdm12](https://github.com/qdm12) (MIT).
