# Paperless-ngx — Podman Quadlet (rootless)

Deploy do [Paperless-ngx](https://docs.paperless-ngx.com) (gerenciador de
documentos self-hosted — OCR, indexação, busca full-text) via Podman
Quadlet, migrado do `docker-compose.sqlite-tika.yml`
[oficial](https://github.com/paperless-ngx/paperless-ngx/blob/dev/docker/compose/docker-compose.sqlite-tika.yml)
(SQLite como banco, com suporte a documentos Office via Tika+Gotenberg).

## Arquitetura

Quatro containers na rede `paperless-ngx-net.network`:

- `paperless-ngx-broker` — Valkey (fila de tarefas assíncronas — OCR,
  indexação — compatível com Redis)
- `paperless-ngx-gotenberg` — converte Office/`.eml` pra PDF antes do OCR
- `paperless-ngx-tika` — extrai texto/metadados de documentos Office
- `paperless-ngx` — a aplicação, expõe `8000` (mapeado pra `8091` no
  host — `8000` já está em uso pelo [Downtify](../media-stack/) neste
  repositório)

`paperless-ngx` só sobe depois que broker e gotenberg reportam `healthy`
(`Requires=`/`After=` no `[Unit]`, mesmo padrão do
[linkwarden](../linkwarden/)/[any-sync-bundle](../any-sync-bundle/)).
**Tika é exceção**: a imagem oficial não tem `curl`/`wget`/nenhuma
ferramenta de rede ([TIKA-3333](https://issues.apache.org/jira/browse/TIKA-3333),
ainda em aberto upstream), então não dá pra declarar `HealthCmd=` nele —
`Requires=`/`After=` ainda garante a *ordem* de start, só não espera ele
ficar de fato pronto pra aceitar conexão. Na prática não costuma ser
problema: o Paperless só fala com o Tika ao processar um documento
Office (assíncrono, via fila), não no próprio startup.

SQLite (banco embutido em `data/`) escolhido de propósito — dispensa um
Postgres a mais só pra este serviço; ver seção Auto-update pro trade-off.

## Arquivos

```
quadlet/
├── paperless-ngx-net.network        # rede dedicada
├── paperless-ngx-broker.container   # Valkey (fila)
├── paperless-ngx-gotenberg.container # conversão Office → PDF
├── paperless-ngx-tika.container     # extração de texto/metadados
└── paperless-ngx.container          # aplicação
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando
- `openssl` (pra gerar o secret)

## Instalação do zero

```bash
# 1. Copiar as units para uma subpasta dedicada
mkdir -p ~/.config/containers/systemd/paperless-ngx
cp quadlet/*.container quadlet/*.network ~/.config/containers/systemd/paperless-ngx/

# 2. Diretórios de dados — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/paperless-ngx/{broker,data,media,export,consume}

# 3. Secret — chave usada pra assinar sessões/tokens
mkdir -p ~/.config/containers/secrets/paperless-ngx
openssl rand -base64 64 | tr -d '\n' > ~/.config/containers/secrets/paperless-ngx/secret-key.txt
chmod 600 ~/.config/containers/secrets/paperless-ngx/secret-key.txt
podman secret create paperless-ngx-secret-key ~/.config/containers/secrets/paperless-ngx/secret-key.txt

# 4. Env não-secreto — copiar o exemplo, ajustar USERMAP_UID/GID pro
#    usuário que roda o Podman (mesmo dono dos volumes acima)
mkdir -p ~/.config/containers/env
cp .env.example ~/.config/containers/env/paperless-ngx.env
sed -i "s/^USERMAP_UID=.*/USERMAP_UID=$(id -u)/;s/^USERMAP_GID=.*/USERMAP_GID=$(id -g)/" \
  ~/.config/containers/env/paperless-ngx.env

# 5. Subir (broker/gotenberg/tika sobem primeiro via Requires=)
systemctl --user daemon-reload
systemctl --user start paperless-ngx
```

Criar o primeiro usuário admin (não vem com senha padrão, diferente de
alguns outros serviços deste repositório):

```bash
podman exec -it paperless-ngx python3 manage.py createsuperuser
```

Acessar via [tsdproxy](../tsdproxy/) (tailnet) em
`https://paperless.<seu-tailnet>.ts.net`, ou local em
`http://localhost:8091`.

**Consumo automático de documentos**: qualquer arquivo colocado em
`volumes/paperless-ngx/consume/` é processado e importado sozinho — a
pasta de "entrada", igual ao `/cwa-book-ingest` do
[Calibre-Web-Automated](../calibre-web-automated/), só que aqui o
arquivo processado é removido da pasta depois (não é storage
permanente).

## OCR em português

A imagem só instala os pacotes Tesseract de inglês/alemão/italiano/
espanhol/francês por padrão. `.env.example` já vem com
`PAPERLESS_OCR_LANGUAGE=por` **e** `PAPERLESS_OCR_LANGUAGES=por` — as
duas são necessárias: a segunda instala o pacote `tesseract-ocr-por` no
primeiro start, a primeira define o idioma usado de fato no
reconhecimento. Setar só uma das duas não funciona (testado — sem
`PAPERLESS_OCR_LANGUAGES`, o idioma nunca fica disponível pro Tesseract
mesmo com `PAPERLESS_OCR_LANGUAGE` apontando pra ele).

## `Notify=healthy` com imagem que já tem HEALTHCHECK embutido

Mesma pegadinha do linkwarden: a imagem oficial do Paperless-ngx já vem
com `HEALTHCHECK` no Dockerfile (`curl ... http://localhost:8000`), mas
isso não basta pro Quadlet — `Notify=healthy` exige `HealthCmd=`
declarado explicitamente no `.container` também, repetindo o mesmo
comando (regra 14 do README raiz).

## Auto-update

Nenhum dos quatro containers tem `AutoUpdate=` — tags explícitas, bump
manual (regra 9 do README raiz). `wud.watch=true` só no container
principal (broker/gotenberg/tika são dependências internas, mesmo
critério já usado em Postgres/Meilisearch/Redis deste repositório).
Motivo pra manual: SQLite embutido (documentos + índice de busca) é dado
real do usuário — healthcheck HTTP não cobre migração de schema quebrada
numa troca de versão, mesmo raciocínio do baikal/vaultwarden.

## Backup & Recuperação

O que importa de verdade é `data/` (banco SQLite + índice) e `media/`
(os documentos em si — o maior em espaço). `export/`/`consume/` são
pastas de trânsito, não precisam de backup. `broker/` é só fila
transiente, recriável do zero sem perda. Parar tudo antes:

```bash
systemctl --user stop paperless-ngx paperless-ngx-broker paperless-ngx-gotenberg paperless-ngx-tika
tar -czf paperless-ngx-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes paperless-ngx
systemctl --user start paperless-ngx
```

O secret (`~/.config/containers/secrets/paperless-ngx/`) também precisa
de backup separado — sem ele, sessões existentes invalidam ao restaurar
num host novo (não impede o acesso aos documentos, só derruba logins
ativos).

## Comandos úteis

```bash
systemctl --user status paperless-ngx paperless-ngx-broker paperless-ngx-gotenberg paperless-ngx-tika
podman logs -f paperless-ngx
podman exec paperless-ngx-broker valkey-cli ping
```

## Créditos

Deploy Quadlet baseado no
[Paperless-ngx](https://github.com/paperless-ngx/paperless-ngx).
Licença original: GPL-3.0.
