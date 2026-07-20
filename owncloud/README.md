# ownCloud — Podman Quadlet (rootless)

Deploy do [ownCloud](https://owncloud.com) Server (sincronização e
compartilhamento de arquivos self-hosted) via Podman Quadlet, seguindo o
[guia oficial de instalação com Docker](https://doc.owncloud.com/server/latest/admin_manual/installation/docker/index.html).

## SQLite — avaliação, não produção

Rodando com **SQLite** de propósito (pedido explícito) — nenhuma
variável `OWNCLOUD_DB_TYPE`/`OWNCLOUD_DB_*` é definida no `.container`, e
SQLite é o que a imagem usa por padrão nesse caso. O próprio projeto
ownCloud **não suporta SQLite em produção**. Trocar pra MySQL/MariaDB ou
Postgres depois se o volume de uso justificar (mesmo padrão de container
extra usado no [linkwarden](../linkwarden/)).

## Arquitetura

Container único, sem Redis (o compose oficial de produção inclui Redis
pra cache/lock — dispensado aqui porque SQLite já é o modo "avaliação",
não faz sentido trazer só uma peça da stack de produção). Expõe `8080`
(mapeado pra `8094` no host).

## Arquivos

```
owncloud.container   # unit principal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando
- `openssl` (pra gerar o secret)

## Instalação do zero

```bash
# 1. Baixar a unit (sem precisar clonar o repositório)
mkdir -p ~/.config/containers/systemd
wget -P ~/.config/containers/systemd/ \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/owncloud/owncloud.container

# 2. Diretório de dados — bind mount exige que já exista antes do start
mkdir -p ~/.config/containers/volumes/owncloud/data

# 3. Secret — senha do admin (criado no primeiro start)
mkdir -p ~/.config/containers/secrets/owncloud
openssl rand -base64 18 | tr -d '\n' > ~/.config/containers/secrets/owncloud/admin-password.txt
chmod 600 ~/.config/containers/secrets/owncloud/admin-password.txt
podman secret create owncloud-admin-password ~/.config/containers/secrets/owncloud/admin-password.txt

# 4. Env não-secreto — baixar o exemplo e editar OWNCLOUD_DOMAIN/
#    OWNCLOUD_TRUSTED_DOMAINS com seu domínio da tailnet
mkdir -p ~/.config/containers/env
wget -O ~/.config/containers/env/owncloud.env \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/owncloud/.env.example
# editar ~/.config/containers/env/owncloud.env

# 5. Subir
systemctl --user daemon-reload
systemctl --user start owncloud
```

Acessar via [tsdproxy](../tsdproxy/) (tailnet) em
`https://owncloud.<seu-tailnet>.ts.net`, ou local em
`http://localhost:8094`. Login com `OWNCLOUD_ADMIN_USERNAME` (default
`admin`) e a senha gerada no passo 3.

## Solução de problemas

**Erro de CSRF/proxy confiável ao acessar via tailnet** — app pensa que
está em HTTP puro, mas o tsdproxy termina TLS na frente. `.env.example`
já vem com
`OWNCLOUD_OVERWRITE_PROTOCOL=https` pra evitar isso de saída — se ainda
assim acontecer, checar `OWNCLOUD_TRUSTED_DOMAINS` (precisa incluir o
hostname exato usado no navegador).

## Auto-update

Sem `AutoUpdate=` — tag explícita (`10.16.3-20260719`), bump manual
(regra 9 do README raiz). Arquivos sincronizados são dado real do
usuário — revisão manual antes de atualizar, mesmo raciocínio do
linkwarden. Ainda mais relevante aqui rodando em SQLite (modo não
suportado oficialmente em produção).

## Backup & Recuperação

```bash
systemctl --user stop owncloud
tar -czf owncloud-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes owncloud
systemctl --user start owncloud
```

## Comandos úteis

```bash
systemctl --user status owncloud
podman logs -f owncloud
podman exec owncloud /usr/bin/healthcheck
```

## Créditos

Deploy Quadlet baseado no [ownCloud](https://github.com/owncloud/core)
Server, usando a imagem oficial
[owncloud/server](https://github.com/owncloud-docker/server).
Licença original: AGPL-3.0.
