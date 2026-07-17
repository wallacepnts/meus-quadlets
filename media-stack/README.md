# Media Stack — Podman Quadlet (rootless)

Deploy de sete serviços [LinuxServer.io](https://docs.linuxserver.io/)
via Podman Quadlet, todos enxergando a mesma raiz de mídia/downloads que
o [Jellyfin](../jellyfin/):

| Serviço | Papel | Porta |
| --- | --- | --- |
| [Prowlarr](https://prowlarr.com) | Gerenciador de indexers, alimenta os três abaixo | `9696` |
| [Sonarr](https://sonarr.tv) | Automação de séries | `8989` |
| [Radarr](https://radarr.video) | Automação de filmes | `7878` |
| [Lidarr](https://lidarr.audio) | Automação de música | `8686` |
| [Bazarr](https://www.bazarr.media) | Legendas automáticas pro Sonarr/Radarr | `6767` |
| [Deluge](https://deluge-torrent.org) | Cliente torrent | `8112` |
| [SABnzbd](https://sabnzbd.org) | Cliente usenet | `8081` (a `8080` já é do [tsdproxy](../tsdproxy/) neste repo) |

## Por que uma raiz de mídia só, compartilhada por todo mundo

Sonarr/Radarr/Lidarr **movem** arquivo de `downloads/` pra dentro de
`media/` quando terminam de importar — se `downloads/` e `media/`
estiverem em filesystems/mounts diferentes (um path pro Deluge, outro
pro Sonarr, outro pro Jellyfin), essa "movida" vira cópia + delete: mais
lento, usa I/O e espaço em disco à toa, e existe uma janela onde o
arquivo já não está mais em `downloads/` nem terminou de aparecer em
`media/`. Com todos os serviços montando a **mesma** `%h/data` como
`/data`, a mesma movida é instantânea (hardlink/rename atômico, mesmo
filesystem).

Estrutura de pastas dentro de `~/data` (criar depois do primeiro start,
pela UI de cada app ou manualmente):

```
~/data/
├── media/
│   ├── movies/
│   ├── tv/
│   └── music/
└── downloads/
    ├── torrents/   # categoria/pasta de destino do Deluge
    └── usenet/      # pasta de destino do SABnzbd
```

**Path único, decidido uma vez, vale pra todos os sete + o Jellyfin** —
ver Instalação. Se sua mídia já mora em outro disco/mount, symlinkar
`~/data` pra lá em vez de criar pasta nova.

## Arquitetura

Sete containers independentes, rede bridge padrão (cada um com sua
`PublishPort=`, sem `.network` dedicado — eles conversam entre si via
HTTP configurado manualmente depois de subir, não via rede Podman
compartilhada). `PUID`/`PGID`/`TZ` num único env file
(`media-stack.env`), reaproveitado pelos sete — ver
[README raiz, regra sobre UserNS vs PUID/PGID](../README.md) pro porquê
dessas imagens usarem esse mecanismo em vez do `UserNS=keep-id` usado no
Jellyfin.

`Prowlarr` não monta `/data` — só gerencia indexers e fala com os outros
via API, não toca em arquivo de mídia/download diretamente.

## Arquivos

```
quadlet/
├── prowlarr.container
├── sonarr.container
├── radarr.container
├── lidarr.container
├── bazarr.container
├── deluge.container
└── sabnzbd.container
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero

```bash
# 1. Copiar as units
mkdir -p ~/.config/containers/systemd
cp quadlet/*.container ~/.config/containers/systemd/

# 2. Raiz de mídia — a ÚNICA decisão de path desta stack inteira (e do
#    Jellyfin). Se a mídia já mora em outro disco/mount, symlinkar em
#    vez de criar pasta nova.
mkdir -p ~/data
# ou: ln -s /caminho/pro/disco/de/midia ~/data

# 3. Diretórios de config — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/media-stack/{prowlarr,sonarr,radarr,lidarr,bazarr,deluge,sabnzbd}/config

# 4. Env compartilhado — PUID/PGID do usuário que roda o Podman (mesmo
#    dono de ~/data, senão os apps não conseguem escrever nela)
mkdir -p ~/.config/containers/env
cat > ~/.config/containers/env/media-stack.env <<EOF
PUID=$(id -u)
PGID=$(id -g)
TZ=America/Sao_Paulo
EOF

# 5. Subir todos
systemctl --user daemon-reload
systemctl --user start prowlarr sonarr radarr lidarr bazarr deluge sabnzbd
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
   apontando pra `/data/media/movies`, `/data/media/tv` etc.

## Auto-update

Nenhum dos sete tem `AutoUpdate=` — tags explícitas, bump manual (regra
9 do README raiz). Todos guardam banco (SQLite, na maioria) com estado
de biblioteca/histórico/configuração de download em `/config` — mesma
cautela do [baikal](../baikal/)/[gitea](../gitea/): healthcheck confere
só se o servidor HTTP responde, não se uma migração de schema rodou
certo numa troca de versão.

## Backup & Recuperação

```bash
systemctl --user stop prowlarr sonarr radarr lidarr bazarr deluge sabnzbd
tar -czf media-stack-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes media-stack
systemctl --user start prowlarr sonarr radarr lidarr bazarr deluge sabnzbd
```

Só as pastas `config/` de cada serviço (API keys, configuração, estado
de download/indexer) — a mídia em si (`~/data/media`) e os downloads
brutos (`~/data/downloads`) ficam fora, mesmo raciocínio do Jellyfin.

## Considerações de segurança — não implementadas aqui

- **Sem VPN no Deluge.** Tráfego de torrent sai direto pelo IP do host.
  Quem se preocupar com isso normalmente roda o cliente torrent atrás de
  um container VPN dedicado (ex.: [gluetun](https://github.com/qdm12/gluetun))
  — não montei isso aqui, é uma peça a mais (mais um container, mais
  configuração de rede) que fica de fora até ser pedida explicitamente.
- **Portas de indexer/download client expostas na tailnet via tsdproxy**
  — como todo resto deste repositório, só alcançável de dentro da
  tailnet, não da internet pública.

## Comandos úteis

```bash
systemctl --user status prowlarr sonarr radarr lidarr bazarr deluge sabnzbd
podman logs -f sonarr   # trocar pelo serviço que quiser
```

## Créditos

Deploy Quadlet baseado nas imagens [LinuxServer.io](https://github.com/linuxserver)
de [Prowlarr](https://github.com/Prowlarr/Prowlarr) (GPL-3.0),
[Sonarr](https://github.com/Sonarr/Sonarr) (GPL-3.0),
[Radarr](https://github.com/Radarr/Radarr) (GPL-3.0),
[Lidarr](https://github.com/Lidarr/Lidarr) (GPL-3.0),
[Bazarr](https://github.com/morpheus65535/bazarr) (GPL-3.0),
[Deluge](https://github.com/deluge-torrent/deluge) (GPL-3.0) e
[SABnzbd](https://github.com/sabnzbd/sabnzbd) (GPL-2.0).
