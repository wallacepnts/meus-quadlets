# Audiobookshelf — Podman Quadlet (rootless)

Deploy do [Audiobookshelf](https://audiobookshelf.org) (servidor de
audiolivros e podcasts, com progresso de leitura sincronizado entre
dispositivos) via Podman Quadlet, seguindo o
[guia oficial de Docker](https://audiobookshelf.org/docs/documentation/install/docker/).

## Arquitetura

Container único, roda como root internamente (a própria imagem não
suporta `PUID`/`PGID` — diferente da maioria das imagens LSIO/Alpine
deste repositório, é assim mesmo por design do projeto). Quatro volumes:

- `config` — banco SQLite e scripts de migração.
- `metadata` — metadados de livro, capas/imagens de autor, logs, backups.
- `audiobooks` / `podcasts` — as bibliotecas de mídia em si (dois
  exemplos do guia oficial; dá pra apontar outras pastas depois pela
  própria UI, desde que sejam bind mounts locais também).

**Aviso da documentação oficial**: `config`/`metadata` precisam estar no
mesmo disco local do host, nunca em compartilhamento de rede (NFS/SMB) —
"pode causar problemas de performance e corrupção do banco". Bind mount
local deste repositório já satisfaz isso; só reforçar se algum dia mover
esses caminhos pra fora do disco local.

## Arquivos

```
audiobookshelf-net.network   # rede bridge isolada
audiobookshelf.container     # unit principal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero

```bash
# 1. Baixar as units (sem precisar clonar o repositório)
mkdir -p ~/.config/containers/systemd
wget -P ~/.config/containers/systemd/ \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/audiobookshelf/audiobookshelf-net.network \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/audiobookshelf/audiobookshelf.container

# 2. Diretórios de dados — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/audiobookshelf/{config,metadata,audiobooks,podcasts}

# 3. Env não-secreto — baixar o exemplo, ajustar TZ se precisar
mkdir -p ~/.config/containers/env
wget -O ~/.config/containers/env/audiobookshelf.env \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/audiobookshelf/.env.example

# 4. Subir
systemctl --user daemon-reload
systemctl --user start audiobookshelf
```

Acessar em `http://<ip-do-host>:13378` (ou via [tsdproxy](../tsdproxy/)
em `https://audiobookshelf.<seu-tailnet>.ts.net`) e criar a conta admin
no primeiro acesso.

Copiar os audiolivros/podcasts pra dentro de
`~/.config/containers/volumes/audiobookshelf/{audiobooks,podcasts}` e
criar as bibliotecas correspondentes na UI (Configurações → Bibliotecas).

## Auto-update

Sem `AutoUpdate=` — tag explícita (`2.35.1`), bump manual (regra 9 do
README raiz). A imagem tem `wget`/healthcheck real (endpoint próprio
`/healthcheck`, testado na prática) — daria pra habilitar
`AutoUpdate=registry` com rollback de verdade, mas mantido manual como
padrão do repositório.

## Backup & Recuperação

```bash
systemctl --user stop audiobookshelf
tar -czf audiobookshelf-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes audiobookshelf
systemctl --user start audiobookshelf
```

`audiobooks/`/`podcasts/` costumam ser grandes — considerar excluir da
tarball e fazer backup deles separadamente se só o progresso/metadados
importar pro backup de rotina.

## Comandos úteis

```bash
systemctl --user status audiobookshelf
podman logs -f audiobookshelf
podman exec audiobookshelf wget -qO- http://127.0.0.1:80/healthcheck
```

## Créditos

Deploy Quadlet baseado no
[Audiobookshelf](https://github.com/advplyr/audiobookshelf) (GPL-3.0).
