# Media Stack — Podman Quadlet (rootless)

Deploy de [Jellyfin](https://jellyfin.org) + [Dispatcharr](https://dispatcharr.github.io/Dispatcharr-Docs/)
+ [Downtify](https://github.com/henriquesebastiao/downtify)
+ nove serviços [LinuxServer.io](https://docs.linuxserver.io/)/[Seerr](https://docs.seerr.dev)
via Podman Quadlet, todos enxergando a mesma raiz de mídia/downloads.

|  | Apps | Descrição | Porta |
| --- | --- | --- | --- |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/jellyfin.svg" width="48" height="48" alt=""> | [Jellyfin](https://jellyfin.org) | Servidor de mídia | `8096` |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/dispatcharr.svg" width="48" height="48" alt=""> | [Dispatcharr](https://dispatcharr.github.io/Dispatcharr-Docs/) | Gerenciador de IPTV (streams, EPG, VOD) | `9191` |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/png/downtify.png" width="48" height="48" alt=""> | [Downtify](https://github.com/henriquesebastiao/downtify) | Downloader de música do Spotify | `8000` |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/prowlarr.svg" width="48" height="48" alt=""> | [Prowlarr](https://prowlarr.com) | Gerenciador de indexers, alimenta os três abaixo | `9696` |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/sonarr.svg" width="48" height="48" alt=""> | [Sonarr](https://sonarr.tv) | Automação de séries | `8989` |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/radarr.svg" width="48" height="48" alt=""> | [Radarr](https://radarr.video) | Automação de filmes | `7878` |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/lidarr.svg" width="48" height="48" alt=""> | [Lidarr](https://lidarr.audio) | Automação de música | `8686` |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/bazarr.svg" width="48" height="48" alt=""> | [Bazarr](https://www.bazarr.media) | Legendas automáticas pro Sonarr/Radarr | `6767` |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/seerr.svg" width="48" height="48" alt=""> | [Seerr](https://docs.seerr.dev) | Pedidos de filme/série, integra com Jellyfin+Sonarr+Radarr | `5055` |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/deluge.svg" width="48" height="48" alt=""> | [Deluge](https://deluge-torrent.org) | Cliente torrent | `8112` |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/sabnzbd.svg" width="48" height="48" alt=""> | [SABnzbd](https://sabnzbd.org) | Cliente usenet | `8081` (a `8080` já é do [tsdproxy](../tsdproxy/) neste repo) |

Um décimo segundo serviço, o [Gluetun](https://github.com/qdm12/gluetun)
(túnel VPN pro Deluge), é **opcional** — ver seção própria abaixo.

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

**Dispatcharr roda em modo AIO** (`DISPATCHARR_ENV=aio`) — um único
container, sem banco/rede próprios: Postgres e Redis rodam *dentro*
dele mesmo (a própria imagem sobe `pg_ctl`/Redis internamente), tudo
num `/data` só. Diferente do modo modular (Postgres/Redis/Celery em
containers separados, como linkwarden/any-sync-bundle) usado
originalmente aqui — trocado a pedido do usuário depois que a imagem
upstream passou a ter um `entrypoint.sh` único cobrindo os dois modos.
Ver seção própria abaixo.

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
jellyfin.container
dispatcharr.container   # modo AIO — Postgres/Redis internos, um container só
downtify.container
prowlarr.container
sonarr.container
radarr.container
lidarr.container
bazarr.container
seerr.container
deluge.container
sabnzbd.container
gluetun.container        # opcional — ver seção VPN abaixo
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero

```bash
# 1. Copiar as units (inclui gluetun.container; só importa se for usar
#    a seção de VPN abaixo — sem ativar, fica parado sem nenhum custo)
mkdir -p ~/.config/containers/systemd
cp *.container ~/.config/containers/systemd/

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
mkdir -p ~/.config/containers/volumes/media-stack/jellyfin/{config,cache}
mkdir -p ~/.config/containers/volumes/media-stack/{prowlarr,sonarr,radarr,lidarr,bazarr,seerr,deluge,sabnzbd}/config
mkdir -p ~/.config/containers/volumes/media-stack/dispatcharr/data
mkdir -p ~/.config/containers/volumes/media-stack/downtify/data
# Downtify baixa em downloads/ (dentro da raiz de mídia), a mesma pasta
# onde o Deluge salva os torrents completos — diferente do resto (passo
# 2 acima já cria a raiz, mas não downloads/, criado pelo Deluge só
# depois do primeiro uso; Downtify bind-monta esse subdiretório direto,
# então precisa existir ANTES do start, não pode esperar).
mkdir -p "$HOME/data/downloads"

# 4. Env compartilhado (LinuxServer.io) — copiar o exemplo e ajustar
#    PUID/PGID pro usuário que roda o Podman (mesmo dono de
#    MEDIA_DATA_DIR, senão os apps não conseguem escrever nela)
mkdir -p ~/.config/containers/env
cp .env.example ~/.config/containers/env/media-stack.env
sed -i "s/^PUID=.*/PUID=$(id -u)/;s/^PGID=.*/PGID=$(id -g)/" \
  ~/.config/containers/env/media-stack.env

# 5. Aplicar a env.d nova (precisa de daemon-reload, não só reiniciar
#    o serviço — é o systemd --user que precisa reler o ambiente)
systemctl --user daemon-reload

# 6. Subir (sem o Gluetun — ver seção própria pra ativar VPN). Sem
#    Requires= entre serviços aqui — Dispatcharr é um container só,
#    Postgres/Redis sobem dentro dele mesmo.
systemctl --user start jellyfin dispatcharr downtify prowlarr sonarr radarr lidarr bazarr seerr deluge sabnzbd
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
8. **Dispatcharr** — assistente inicial pede conta admin. Depois,
   Settings → M3U/EPG → adicionar suas playlists IPTV (M3U) e fontes de
   EPG (XMLTV) — é a partir daí que ele monta o guia de canais e o
   proxy de stream. Sem afinidade com o resto da stack (não fala com
   Sonarr/Radarr/Jellyfin via API) — funciona isolado.

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

## Dispatcharr: modo AIO, Postgres e Redis embutidos

`dispatcharr.container` roda em modo AIO
(`Environment=DISPATCHARR_ENV=aio`) — a própria imagem sobe Postgres e
Redis internamente (via `pg_ctl`/uwsgi attach-daemon no
`entrypoint.sh`), tudo dentro de um único `/data:Z` (banco em
`/data/db`, chave Django em `/data/jwt`, config/gravações no resto).
Diferente do modo "modular" (Postgres/Redis externos, containers
separados) que este repositório usava originalmente — trocado a pedido
do usuário depois que a imagem upstream passou a ter um `entrypoint.sh`
único cobrindo os dois modos, o que tornou o AIO viável sem abrir mão
de nada.

**Sem secret**: o modo AIO usa uma senha fixa (`secret`) pro Postgres
interno, que só é alcançável via socket Unix *dentro* do próprio
container — nunca exposta na rede, então não há segredo real pra
gerenciar aqui (diferente do modo modular, que expunha o Postgres numa
rede Podman compartilhada e por isso precisava de senha real).

**Primeiro boot é mais lento** que os outros serviços desta stack:
`initdb` do Postgres embutido + migração do schema Django + Redis +
Celery + nginx + uwsgi, tudo em sequência — testado na prática, dentro
da margem de `TimeoutStartSec=300` já usada aqui.

## Downtify: baixa na mesma pasta do Deluge

`downtify` monta `${MEDIA_DATA_DIR}/downloads:/downloads:Z` — a mesma
`downloads/` onde o Deluge (`torrents/`) e o SABnzbd (`usenet/`) também
gravam, em vez de um diretório isolado só dele (decisão explícita, não
o padrão do projeto original). Como o mount é a pasta `downloads/`
inteira, os arquivos do Downtify ficam soltos na raiz dela, ao lado das
subpastas `torrents/`/`usenet/` dos outros dois. Precisa de
`MEDIA_DATA_DIR` configurado em `~/.config/environment.d/` antes do
start, igual ao resto da stack (ver Instalação acima) — sem isso o
Volume= não expande e o start falha.

Sem credenciais de API pra configurar: o pipeline (scraping do Spotify
+ busca no YouTube Music) é autocontido, não depende de mais nada da
stack (Prowlarr, indexers, etc.).

`DNS=1.1.1.1`/`DNS=1.0.0.1` no `.container` — recomendação do próprio
projeto (o `docker-compose.yml` oficial já vem assim), já que a
resolução confiável de `open.spotify.com`/`music.youtube.com` é
crítica pro pipeline funcionar.

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
# 1. Credenciais do provedor de VPN — copiar o exemplo e editar (ver
#    lista de provedores suportados:
#    https://github.com/qdm12/gluetun-wiki/tree/main/setup/providers)
cp gluetun.env.example ~/.config/containers/env/gluetun.env
# editar ~/.config/containers/env/gluetun.env: VPN_SERVICE_PROVIDER,
# WIREGUARD_PRIVATE_KEY, WIREGUARD_ADDRESSES, SERVER_COUNTRIES
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
(regra 9 do README raiz; `gluetun.container` e `dispatcharr.container`
deste repo são exceção consciente, ficam em `:latest` porque os
respectivos projetos não publicam releases versionadas de forma
estável — reavaliar se isso mudar).
Jellyfin, os apps LinuxServer.io e o Seerr guardam banco (SQLite, a
maioria) com estado de biblioteca/histórico/configuração de download em
`/config` — mesma cautela do [baikal](../baikal/)/[gitea](../gitea/):
healthcheck confere só se o servidor HTTP responde, não se uma migração
de schema rodou certo numa troca de versão.

**Dispatcharr é o único caso deste repositório com visibilidade real do
WUD mesmo sem tag semver:**

```ini
Label=wud.watch=true
Label=wud.watch.digest=true
```

Sem tag versionada pra comparar, o WUD normalmente não teria sinal
nenhum (ver README do [wud](../wud/), seção "Tags não-semver não são
observadas") — `wud.watch.digest` contorna isso comparando o digest da
imagem publicada em `:latest` contra o que está rodando. Como o
Postgres embutido do Dispatcharr guarda dados reais (canais, EPG, DVR)
e o projeto ainda está em desenvolvimento ativo, a atualização continua
manual mesmo com essa visibilidade:

```bash
systemctl --user stop dispatcharr
podman pull ghcr.io/dispatcharr/dispatcharr:latest
systemctl --user start dispatcharr
```

**Fazer backup antes de atualizar** (seção abaixo) — em modo AIO, uma
migração de schema malsucedida afeta o único container que existe, sem
a rede de segurança de containers isolados que o modo modular tinha.

## Backup & Recuperação

```bash
systemctl --user stop jellyfin dispatcharr downtify prowlarr sonarr radarr lidarr bazarr seerr deluge sabnzbd
tar -czf media-stack-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes media-stack
systemctl --user start jellyfin dispatcharr downtify prowlarr sonarr radarr lidarr bazarr seerr deluge sabnzbd
```

Só as pastas `config/`/`cache/` de cada serviço (API keys, configuração,
estado de download/indexer, biblioteca/histórico do Jellyfin) — a mídia
em si e os downloads brutos ficam fora, fora de
`~/.config/containers/volumes/`, gerenciados separadamente por quem
instalou. Se estiver usando o Gluetun,
`~/.config/containers/env/gluetun.env` (credenciais de VPN) também
precisa de backup separado — sem ele, só recriar do zero com o provedor.

No Dispatcharr (modo AIO), `volumes/media-stack/dispatcharr/data`
guarda tudo — banco (`data/db`, canais/playlists/EPG/usuários), chave
Django (`data/jwt`) e o resto (logos em cache, gravações DVR). Um
`tar` a frio funciona (backup de arquivo do Postgres embutido, válido
porque tudo pára junto), mas pra restaurar em outra instância —
migração, versão incompatível de Postgres — `pg_dump`/`pg_restore` é
mais confiável que copiar `data/db` cru:

```bash
podman exec dispatcharr su - dispatch -c \
  "pg_dump -h /var/run/postgresql -U dispatch -d dispatcharr --format=custom -f /tmp/dispatcharr.pgdump"
podman cp dispatcharr:/tmp/dispatcharr.pgdump ./dispatcharr-backup.pgdump
```

No Downtify, `data/` é o que importa (playlists monitoradas,
preferências) — `downloads/` é só o resultado final, reconstruível
baixando de novo se precisar.

## Considerações de segurança — não implementadas aqui

- **Portas de indexer/download client expostas na tailnet via tsdproxy**
  — como todo resto deste repositório, só alcançável de dentro da
  tailnet, não da internet pública.

## Comandos úteis

```bash
systemctl --user status jellyfin dispatcharr downtify prowlarr sonarr radarr lidarr bazarr seerr deluge sabnzbd
podman logs -f sonarr   # trocar pelo serviço que quiser
podman exec dispatcharr su - dispatch -c "psql -h /var/run/postgresql -U dispatch -d dispatcharr -c 'SELECT 1;'"
```

## Créditos

Deploy Quadlet baseado no [Jellyfin](https://github.com/jellyfin/jellyfin)
(GPL-2.0), no [Dispatcharr](https://github.com/Dispatcharr/Dispatcharr)
(AGPL-3.0), no [Downtify](https://github.com/henriquesebastiao/downtify)
(GPL-3.0), de [Henrique Sebastião](https://github.com/henriquesebastiao),
e nas imagens [LinuxServer.io](https://github.com/linuxserver)
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
