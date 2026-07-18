# Calibre-Web-Automated — Podman Quadlet (rootless)

Deploy do [Calibre-Web-Automated](https://github.com/crocodilestick/Calibre-Web-Automated)
(biblioteca de ebooks self-hosted — leitura web + conversão/metadados
automáticos via Calibre) via Podman Quadlet, usando a imagem oficial do
projeto.

## Arquitetura

Container único, imagem baseada em `linuxserver/baseimage-ubuntu` — usa
`PUID`/`PGID` (usermod interno, precisa rodar como root de verdade dentro
do próprio namespace do container), **não** `UserNS=keep-id`: mesmo
mecanismo dos containers LinuxServer.io do [media-stack](../media-stack/),
misturar os dois quebra a imagem.

Três volumes:
- `/config` — configuração da aplicação + banco (`metadata.db`)
- `/cwa-book-ingest` — pasta de **entrada**, não de armazenamento: tudo
  que cai aqui é processado e importado pra biblioteca automaticamente,
  depois **removido** dessa pasta
- `/calibre-library` — a biblioteca de verdade; se estiver vazia no
  primeiro start, a imagem cria uma nova ali

Ficou de fora da raiz de mídia compartilhada do [media-stack](../media-stack/)
de propósito — lá a raiz única existe porque Sonarr/Radarr/Lidarr
**movem** arquivo de `downloads/` pra `media/` (precisa ser o mesmo
filesystem, ver motivo na seção própria daquele README); aqui não tem
indexer/torrent alimentando `/cwa-book-ingest` automaticamente, é um drop
manual — não existe o mesmo problema de mount cruzado.

## Arquivos

```
quadlet/
└── calibre-web-automated.container   # unit principal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando
- Se você já tem uma biblioteca Calibre existente: parar a instância
  antiga antes, copiar a pasta pra dentro de `volumes/.../library` (ver
  Instalação)

## Instalação do zero

```bash
# 1. Copiar a unit
mkdir -p ~/.config/containers/systemd
cp quadlet/calibre-web-automated.container ~/.config/containers/systemd/

# 2. Diretórios de dados — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/calibre-web-automated/{config,ingest,library}

# 3. Env não-secreto — copiar o exemplo, ajustar PUID/PGID pro usuário
#    que roda o Podman (mesmo dono dos volumes acima)
mkdir -p ~/.config/containers/env
cp .env.example ~/.config/containers/env/calibre-web-automated.env
sed -i "s/^PUID=.*/PUID=$(id -u)/;s/^PGID=.*/PGID=$(id -g)/" \
  ~/.config/containers/env/calibre-web-automated.env

# 4. Subir
systemctl --user daemon-reload
systemctl --user start calibre-web-automated
```

Acessar via [tsdproxy](../tsdproxy/) (tailnet) em
`https://calibre-web.<seu-tailnet>.ts.net`, ou local em
`http://localhost:8090`. Usuário/senha padrão no primeiro acesso:
`admin`/`admin123` — trocar logo em Configurações.

**Migrando de um Calibre-Web "normal"**: parar a instância antiga, copiar
a pasta de config dela pra dentro de `volumes/calibre-web-automated/config/`
antes do primeiro start daqui — carrega usuários/config existentes.

**Plugins do Calibre** (opcional, WIP segundo o projeto): montar um quarto
volume `.../plugins:/config/.config/calibre/plugins:Z` e copiar
`customize.py.json` pra dentro de `config/.config/calibre/` — não incluído
por padrão nesta unit por ser um caso de uso avançado.

## Auto-update

Sem `AutoUpdate=` — tag explícita (`v4.0.6`), bump manual (regra 9 do
README raiz). A imagem tem `curl`/healthcheck real (daria pra habilitar
com rollback de verdade), mas a biblioteca inteira (banco `metadata.db` +
arquivos) é dado real do usuário — prefiro revisão manual antes de trocar
de versão, mesmo raciocínio do baikal/vaultwarden.

## Backup & Recuperação

```bash
systemctl --user stop calibre-web-automated
tar -czf calibre-web-automated-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes calibre-web-automated
systemctl --user start calibre-web-automated
```

`config/` (banco + preferências) é o que importa de verdade; `library/`
costuma ser o maior em espaço — considerar backups separados se a
biblioteca for grande.

## Comandos úteis

```bash
systemctl --user status calibre-web-automated
podman logs -f calibre-web-automated
```

## Créditos

Deploy Quadlet usando a imagem oficial
[crocodilestick/Calibre-Web-Automated](https://github.com/crocodilestick/Calibre-Web-Automated)
(GPL-3.0).
