# Immich — Podman Quadlet (rootless)

Deploy do [Immich](https://immich.app) (backup e organização de fotos/
vídeos self-hosted, com reconhecimento facial e busca smart — alternativa
ao Google Photos) via Podman Quadlet, migrado do
[`docker-compose.rootless.yml`](https://github.com/immich-app/immich/blob/main/docker/docker-compose.rootless.yml)
oficial (a variante já pensada pra Docker/Podman rootless — uid/gid
fixos em vez de root).

## Arquitetura

Quatro containers na rede `immich-net.network`:

- `immich-postgres` — Postgres com extensão de vetor (VectorChord/
  pgvecto.rs, imagem própria do projeto — não é Postgres genérico) —
  dados + índice de busca por similaridade
- `immich-redis` — fila de jobs assíncronos (Valkey, compatível com Redis)
- `immich-machine-learning` — reconhecimento facial, busca por
  texto/imagem (CLIP), tagueamento automático
- `immich` — a aplicação, expõe `2283`

`immich` só sobe depois que postgres e redis reportam `healthy`
(`Requires=`/`After=`, mesmo padrão do
[paperless-ngx](../paperless-ngx/)/[karakeep](../karakeep/)) — o
compose oficial não lista `machine-learning` como dependência de start
(a app só chama ele por HTTP quando precisa, não trava o boot esperando).

**Hostnames fixos**: o Immich resolve `database`/`redis`/
`immich-machine-learning` como endereço **padrão** desses três serviços
(não são só variáveis de ambiente configuráveis à toa — `DB_HOSTNAME`/
`REDIS_HOSTNAME` têm esses valores como default, e o endereço de ML fica
salvo nas configurações da própria aplicação depois do primeiro start).
Por isso os três containers de dependência usam `NetworkAlias=` com
esses nomes exatos, sem precisar declarar as variáveis de host
explicitamente.

**Hardening replicado do compose oficial**: `NoNewPrivileges=true` +
`--cap-drop=NET_RAW` nos quatro containers, `UserNS=keep-id` (a variante
"rootless" já roda como uid/gid fixo `1000:1000`, sem usermod interno —
mesmo motivo do Jellyfin/Seerr no [media-stack](../media-stack/)).

## Arquivos

```
immich-net.network                 # rede dedicada
immich-redis.container             # fila (Valkey)
immich-postgres.container          # Postgres + extensão de vetor
immich-machine-learning.container  # reconhecimento facial / busca smart
immich.container                   # aplicação
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando
- `openssl` (pra gerar o secret)
- RAM de sobra pro `immich-machine-learning` — os modelos de reconhecimento
  facial/CLIP consomem memória real quando carregados; num homelab
  pequeno, vale acompanhar o consumo nos primeiros dias de uso

## Instalação do zero

```bash
# 1. Baixar as units pra uma subpasta dedicada (sem precisar clonar o
#    repositório)
mkdir -p ~/.config/containers/systemd/immich
for f in immich-net.network immich-redis.container immich-postgres.container \
         immich-machine-learning.container immich.container; do
  wget -P ~/.config/containers/systemd/immich/ \
    "https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/immich/$f"
done

# 2. Diretórios de dados — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/immich/{upload,postgres,redis,ml-cache,ml-dotcache,ml-config}

# 3. Secret — senha do Postgres, mesma usada nos dois containers
mkdir -p ~/.config/containers/secrets/immich
openssl rand -base64 24 | tr -d '\n' > ~/.config/containers/secrets/immich/db-password.txt
chmod 600 ~/.config/containers/secrets/immich/db-password.txt
podman secret create immich-db-password ~/.config/containers/secrets/immich/db-password.txt

# 4. Env não-secreto — baixar o exemplo
mkdir -p ~/.config/containers/env
wget -O ~/.config/containers/env/immich.env \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/immich/.env.example

# 5. Subir (redis e postgres sobem primeiro via Requires=)
systemctl --user daemon-reload
systemctl --user start immich
```

Acessar via [tsdproxy](../tsdproxy/) (tailnet) em
`https://immich.<seu-tailnet>.ts.net`, ou local em
`http://localhost:2283`. Criar a primeira conta (vira admin
automaticamente) pela própria UI, sem usuário/senha padrão.

**Apps móveis** (iOS/Android) sincronizam fotos automaticamente — apontar
pro mesmo endereço usado no navegador, na tela de login do app.

## Auto-update

Sem `AutoUpdate=` — tags explícitas (`v3.0.3` app/ML; Postgres e Redis
travados na combinação tag+digest exata do compose oficial), bump manual
(regra 9 do README raiz). Fotos/vídeos e o índice de reconhecimento
facial são dado real e irrecuperável do usuário — revisão manual antes
de atualizar, e checar o changelog: migrations de banco entre versões
maiores do Immich não são incomuns.

## Backup & Recuperação

O que importa de verdade, em ordem de criticidade: `upload/` (as fotos e
vídeos em si — irrecuperável se perdido) e `postgres/` (metadados, álbuns,
faces reconhecidas, compartilhamentos — recriável reprocessando as fotos,
mas com bastante trabalho). `redis/` é só fila de jobs, `ml-*` é cache de
modelo, ambos recriáveis do zero sem perda.

```bash
systemctl --user stop immich immich-machine-learning immich-postgres immich-redis
tar -czf immich-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes immich
systemctl --user start immich
```

O secret (`~/.config/containers/secrets/immich/`) também precisa de
backup separado.

## Comandos úteis

```bash
systemctl --user status immich immich-machine-learning immich-postgres immich-redis
podman logs -f immich
podman exec immich-postgres healthcheck.sh
```

## Créditos

Deploy Quadlet baseado no [Immich](https://github.com/immich-app/immich).
Licença original: AGPL-3.0.
