# Karakeep — Podman Quadlet (rootless)

Deploy do [Karakeep](https://karakeep.app) (gerenciador de bookmarks —
antigo Hoarder, renomeado pelo projeto) via Podman Quadlet, migrado do
`docker-compose.yml`
[oficial](https://github.com/karakeep-app/karakeep/blob/main/docker/docker-compose.yml).

## Arquitetura

Três containers na rede `karakeep-net.network`:

- `karakeep-chrome` — Chrome headless (`alpine-chrome`), usado pelo
  crawler pra renderizar página e tirar screenshot/arquivar o conteúdo
  de cada link salvo. Sem volume — stateless, cada restart é uma sessão
  nova.
- `karakeep-meilisearch` — busca full-text sobre os bookmarks salvos
- `karakeep` — a aplicação, expõe `3000` (mapeado pra `8092` no host)

Banco **SQLite embutido** em `/data` (não precisa de Postgres — diferente
do [linkwarden](../linkwarden/), que é o app mais parecido neste
repositório).

`karakeep` só sobe depois que chrome e meilisearch reportam `healthy`
(`Requires=`/`After=` no `[Unit]`, mesmo padrão do
[linkwarden](../linkwarden/)/[paperless-ngx](../paperless-ngx/)).

## Arquivos

```
karakeep-net.network            # rede dedicada
karakeep-chrome.container       # Chrome headless (crawler)
karakeep-meilisearch.container  # busca full-text
karakeep.container              # aplicação
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando
- `openssl` (pra gerar os segredos)

## Instalação do zero

```bash
# 1. Copiar as units para uma subpasta dedicada
mkdir -p ~/.config/containers/systemd/karakeep
cp *.container *.network ~/.config/containers/systemd/karakeep/

# 2. Diretórios de dados — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/karakeep/{data,meilisearch}

# 3. Segredos — gerados uma vez, nunca versionados. O mesmo
#    karakeep-meili-key é usado nos dois containers (meilisearch valida
#    a chave, karakeep autentica com ela).
mkdir -p ~/.config/containers/secrets/karakeep
openssl rand -base64 36 | tr -d '\n' > ~/.config/containers/secrets/karakeep/nextauth-secret.txt
openssl rand -base64 36 | tr -dc 'A-Za-z0-9' > ~/.config/containers/secrets/karakeep/meili-master-key.txt
chmod 600 ~/.config/containers/secrets/karakeep/*.txt

podman secret create karakeep-nextauth-secret ~/.config/containers/secrets/karakeep/nextauth-secret.txt
podman secret create karakeep-meili-key ~/.config/containers/secrets/karakeep/meili-master-key.txt

# 4. Env não-secreto — copiar o exemplo e editar NEXTAUTH_URL: precisa
#    bater exatamente com o endereço usado no navegador
mkdir -p ~/.config/containers/env
cp .env.example ~/.config/containers/env/karakeep.env
# editar ~/.config/containers/env/karakeep.env: NEXTAUTH_URL

# 5. Subir (chrome e meilisearch sobem primeiro via Requires=)
systemctl --user daemon-reload
systemctl --user start karakeep
```

Acessar via [tsdproxy](../tsdproxy/) (tailnet) em
`https://karakeep.<seu-tailnet>.ts.net` — é o padrão deste setup. Pra
acesso só local em vez disso, usar `http://localhost:8092` **e** trocar o
`NEXTAUTH_URL` em `karakeep.env` pra bater (mesma regra do NextAuth já
documentada no [linkwarden](../linkwarden/) — só uma URL canônica).

Criar a primeira conta pela própria UI (sem usuário/senha padrão).
Depois, considerar `DISABLE_SIGNUPS=true` no `.env` (instância pessoal,
sem motivo pra deixar cadastro aberto).

## Sincronizar bookmarks do navegador (Floccus)

O [Floccus](https://floccus.org) (extensão de navegador — Chrome,
Firefox, Edge, Brave, Vivaldi, Opera) sincroniza os bookmarks nativos do
navegador com um backend próprio, com suporte nativo ao Karakeep desde a
versão 5.6. Sincronização é bidirecional: salvar um link no navegador
manda ele pro Karakeep, e salvar/editar pela UI do Karakeep reflete de
volta nos bookmarks do navegador (e nos outros navegadores que
sincronizam com a mesma conta).

1. Gerar uma API key no Karakeep: ícone de usuário (canto superior
   direito) → **User Settings** → **API Keys** → **New API Key** → dar um
   nome → **Create**. A chave só aparece uma vez nesse momento
   (formato `ak2_<id>_<segredo>`) — copiar antes de fechar.
2. Instalar o Floccus no navegador e, no assistente de configuração,
   escolher **Karakeep** como tipo de conta — preencher a URL do servidor
   (`https://karakeep.<seu-tailnet>.ts.net`) e a API key do passo 1.
3. Escolher quais pastas de bookmark sincronizar (o Floccus permite
   restringir a uma subpasta em vez do navegador inteiro).

## `Notify=healthy` com imagem que já tem HEALTHCHECK embutido

Mesma pegadinha do linkwarden/paperless-ngx: a imagem oficial do
Karakeep já vem com `HEALTHCHECK` no Dockerfile
(`wget --spider http://127.0.0.1:3000/api/health`), mas isso não basta
pro Quadlet — `Notify=healthy` exige `HealthCmd=` declarado
explicitamente no `.container` também, repetindo o mesmo comando (regra
14 do README raiz).

## Auto-update

Nenhum dos três containers tem `AutoUpdate=` — tags explícitas, bump
manual (regra 9 do README raiz). O `docker-compose.yml` oficial usa
`${KARAKEEP_VERSION:-release}` (tag flutuante, sempre a última release
estável) — trocado aqui por uma versão exata (`0.32.0`) de propósito,
mesmo padrão do resto do repositório. Meilisearch e Chrome nas versões
recomendadas pelo compose oficial — trocar sem checar compatibilidade
pode quebrar a busca ou o crawler.

## Backup & Recuperação

O que importa de verdade é `data/` (SQLite embutido + assets/screenshots
arquivados). `meilisearch/` é um índice de busca — recriável do zero
reindexando, mas mais rápido restaurar do que reindexar tudo de novo se
a biblioteca for grande.

```bash
systemctl --user stop karakeep karakeep-chrome karakeep-meilisearch
tar -czf karakeep-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes karakeep
systemctl --user start karakeep
```

Os segredos (`~/.config/containers/secrets/karakeep/`) também precisam
de backup separado — sem o `NEXTAUTH_SECRET`, sessões existentes
invalidam ao restaurar num host novo.

## Comandos úteis

```bash
systemctl --user status karakeep karakeep-chrome karakeep-meilisearch
podman logs -f karakeep
podman exec karakeep-chrome wget -qO- http://127.0.0.1:9222/json/version
```

## Créditos

Deploy Quadlet baseado no [Karakeep](https://github.com/karakeep-app/karakeep)
(antigo Hoarder). Licença original: AGPL-3.0.
