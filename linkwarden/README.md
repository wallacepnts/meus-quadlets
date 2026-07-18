# Linkwarden — Podman Quadlet (rootless)

Deploy do [Linkwarden](https://linkwarden.app) (gerenciador de
links/bookmarks self-hosted) via Podman Quadlet, migrado do
`docker-compose.yml` oficial (Postgres + Meilisearch).

## Arquitetura

Três containers na rede `linkwarden-net.network`:

- `linkwarden-postgres` — Postgres 16 (dados)
- `linkwarden-meilisearch` — Meilisearch (busca)
- `linkwarden` — a aplicação, expõe `3000` (mapeado pra `3001` no host —
  `3000` já está em uso pela [homepage](../homepage/) neste repositório)

`linkwarden` só sobe depois que postgres e meilisearch reportam `healthy`
(`Requires=`/`After=` no `[Unit]`, mesmo padrão do
[any-sync-bundle](../any-sync-bundle/)).

## Arquivos

```
linkwarden-net.network             # rede dedicada
linkwarden-postgres.container      # Postgres 16
linkwarden-meilisearch.container   # Meilisearch, tag presa (compatibilidade)
linkwarden.container               # aplicação
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando
- `openssl` (pra gerar os segredos)

## Instalação do zero

```bash
# 1. Baixar as units pra uma subpasta dedicada (sem precisar clonar o
#    repositório)
mkdir -p ~/.config/containers/systemd/linkwarden
for f in linkwarden-net.network linkwarden-postgres.container \
         linkwarden-meilisearch.container linkwarden.container; do
  wget -P ~/.config/containers/systemd/linkwarden/ \
    "https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/linkwarden/$f"
done

# 2. Diretórios de dados — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/linkwarden/{postgres,meili_data,data}

# 3. Segredos — gerados uma vez, nunca versionados. DATABASE_URL embute a
#    MESMA senha usada em POSTGRES_PASSWORD (não tem como evitar essa
#    duplicação: um vira env var crua pro Postgres, o outro faz parte da
#    connection string que o Linkwarden usa).
mkdir -p ~/.config/containers/secrets/linkwarden
POSTGRES_PW=$(openssl rand -hex 24)
echo -n "$POSTGRES_PW" > ~/.config/containers/secrets/linkwarden/postgres-password.txt
openssl rand -base64 32 | tr -d '\n' > ~/.config/containers/secrets/linkwarden/nextauth-secret.txt
openssl rand -hex 24 | tr -d '\n' > ~/.config/containers/secrets/linkwarden/meili-master-key.txt
echo -n "postgresql://postgres:${POSTGRES_PW}@postgres:5432/postgres" > ~/.config/containers/secrets/linkwarden/database-url.txt
chmod 600 ~/.config/containers/secrets/linkwarden/*.txt

podman secret create linkwarden-postgres-password ~/.config/containers/secrets/linkwarden/postgres-password.txt
podman secret create linkwarden-nextauth-secret ~/.config/containers/secrets/linkwarden/nextauth-secret.txt
podman secret create linkwarden-meili-key ~/.config/containers/secrets/linkwarden/meili-master-key.txt
podman secret create linkwarden-database-url ~/.config/containers/secrets/linkwarden/database-url.txt

# 4. Env não-secreto — copiar o exemplo e editar NEXTAUTH_URL: precisa
#    bater exatamente com o endereço usado no navegador (NextAuth valida
#    isso pra cookies/CSRF). O .container já vem com labels do tsdproxy
#    (nó "linkwarden" na tailnet), então o padrão do exemplo é o
#    endereço da tailnet.
mkdir -p ~/.config/containers/env
wget -O ~/.config/containers/env/linkwarden.env \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/linkwarden/.env.example
# editar ~/.config/containers/env/linkwarden.env: NEXTAUTH_URL

# 5. Subir (postgres e meilisearch sobem primeiro via Requires=)
systemctl --user daemon-reload
systemctl --user start linkwarden
```

Acessar via [tsdproxy](../tsdproxy/) (tailnet) em
`https://linkwarden.<seu-tailnet>.ts.net` — é o padrão deste setup. Pra
acesso só local em vez disso, usar `http://localhost:3001` **e** trocar o
`NEXTAUTH_URL` em `linkwarden.env` pra bater (não dá pra usar os dois ao
mesmo tempo — diferente de `ANY_SYNC_BUNDLE_INIT_EXTERNAL_ADDRS`, o
NextAuth só aceita uma URL canônica).

## `Notify=healthy` com imagem que já tem HEALTHCHECK embutido

A imagem oficial do Linkwarden já vem com um `HEALTHCHECK` no próprio
Dockerfile (`curl --fail http://127.0.0.1:3000/`). Isso **não é
suficiente** pra usar `Notify=healthy` no Quadlet — o Podman recusa subir
com `sdnotify policy "healthy" requires a healthcheck to be set` mesmo com
o healthcheck da imagem presente. É preciso declarar `HealthCmd=`
explicitamente no `.container` também (replicando o mesmo comando), senão
`Notify=healthy` falha sempre, não importa a imagem.

## Auto-update

Nenhum dos três containers tem `AutoUpdate=` — tags explícitas, bump
manual (regra 9 do README raiz). O Meilisearch em particular: a versão
(`v1.12.8`) é a que o `docker-compose.yml` oficial do Linkwarden recomenda
— trocar sem checar compatibilidade pode quebrar a busca.

## Backup & Recuperação

Três volumes; o mais crítico é o Postgres (dados de verdade — links,
usuários, tags). Parar tudo antes:

```bash
systemctl --user stop linkwarden linkwarden-postgres linkwarden-meilisearch
tar -czf linkwarden-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes linkwarden
systemctl --user start linkwarden
```

Os segredos (`~/.config/containers/secrets/linkwarden/`) também precisam
de backup separado — sem eles, restaurar os dados não adianta (o
`DATABASE_URL` não vai bater com a senha do Postgres restaurado a menos
que seja o mesmo).

## Comandos úteis

```bash
systemctl --user status linkwarden linkwarden-postgres linkwarden-meilisearch
podman logs -f linkwarden
podman exec linkwarden-postgres pg_isready -U postgres
```

## Créditos

Deploy Quadlet baseado no [Linkwarden](https://github.com/linkwarden/linkwarden).
Licença original: AGPL-3.0.
