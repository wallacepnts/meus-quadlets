# Gitea — Podman Quadlet (rootless)

Deploy do [Gitea](https://gitea.com) (fórum/servidor Git self-hosted) via
Podman Quadlet, baseado no [guia oficial de Docker](https://docs.gitea.com/installation/install-with-docker).

## Decisões deste deploy

- **SQLite embutido**, não Postgres externo. Diferente do
  [linkwarden](../linkwarden/), aqui é uso pessoal/homelab — SQLite é o
  que o próprio Gitea recomenda pra esse cenário; Postgres só vale a
  complexidade extra (mais um container, mais secrets) em produção com
  múltiplos usuários simultâneos.
- **Sem Git via SSH** — só HTTP/HTTPS. A porta `22` do container (SSH
  interno do Gitea) não é publicada; simplifica o setup e evita long-term
  gerenciar mais uma porta exposta. Clone/push funcionam normalmente via
  HTTPS com usuário/senha ou token.

## Arquitetura

Container único, Alpine + s6-overlay. Um volume só (`/data`) guarda
banco SQLite, repositórios, configuração (`app.ini`) e anexos.

## Arquivos

```
quadlet/
└── gitea.container   # unit principal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero

```bash
# 1. Copiar a unit
mkdir -p ~/.config/containers/systemd
cp quadlet/gitea.container ~/.config/containers/systemd/

# 2. Diretório de dados — bind mount exige que já exista antes do start
mkdir -p ~/.config/containers/volumes/gitea/data

# 3. Secrets — gerados com a própria imagem, formato específico do Gitea
#    (não é openssl rand genérico)
mkdir -p ~/.config/containers/secrets/gitea
podman run --rm docker.io/gitea/gitea:1.27.0 gitea generate secret SECRET_KEY \
  > ~/.config/containers/secrets/gitea/secret-key.txt
podman run --rm docker.io/gitea/gitea:1.27.0 gitea generate secret INTERNAL_TOKEN \
  > ~/.config/containers/secrets/gitea/internal-token.txt
chmod 600 ~/.config/containers/secrets/gitea/*.txt

podman secret create gitea-secret-key ~/.config/containers/secrets/gitea/secret-key.txt
podman secret create gitea-internal-token ~/.config/containers/secrets/gitea/internal-token.txt

# 4. Env não-secreto — copiar o exemplo (pré-preenche o assistente de
#    instalação: DB e domínio já vêm certos, só falta criar a conta admin
#    na UI)
mkdir -p ~/.config/containers/env
cp .env.example ~/.config/containers/env/gitea.env
# editar ~/.config/containers/env/gitea.env: GITEA__server__DOMAIN e
# GITEA__server__ROOT_URL

# 5. Subir
systemctl --user daemon-reload
systemctl --user start gitea
```

Acessar via [tsdproxy](../tsdproxy/) (tailnet) em
`https://gitea.<seu-tailnet>.ts.net`, ou local em
`http://localhost:3002` — a raiz redireciona pro assistente de
instalação na primeira vez (igual o [baikal](../baikal/)); com
`DB_TYPE`/`DOMAIN`/`ROOT_URL` já pré-preenchidos pelo env, só falta
criar a conta admin.

**Só acesso local (sem tsdproxy)?** Trocar `GITEA__server__DOMAIN` e
`GITEA__server__ROOT_URL` em `gitea.env` pra `localhost`/`http://localhost:3002/`
antes do primeiro start — assim como o `NEXTAUTH_URL` do
[linkwarden](../linkwarden/), `ROOT_URL` fica gravado no `app.ini` depois
da instalação; mudar depois exige editar o arquivo direto (ver
`~/.config/containers/volumes/gitea/data/gitea/conf/app.ini`).

## Habilitando Git via SSH depois, se mudar de ideia

Adicionar ao `.container`:

```ini
PublishPort=2222:22
```

E no `gitea.env`:

```
GITEA__server__SSH_DOMAIN=gitea.<seu-tailnet>.ts.net
GITEA__server__SSH_PORT=2222
```

`2222`, não `22` — porta padrão do host fica livre pra um sshd de
verdade, se algum dia for ligado (mesma cautela do restante deste repo).

## Auto-update

Sem `AutoUpdate=` — tag explícita (`1.27.0`), bump manual (regra 9 do
README raiz). Imagem Alpine com `wget`, `HealthCmd` real configurado —
daria pra habilitar auto-update de verdade, mas releases do Gitea às
vezes exigem migração de banco na subida (mesmo tipo de cautela do
[linkwarden](../linkwarden/)); revisão manual antes de trocar de versão.

## Backup & Recuperação

Um volume só, mas com o SQLite ativo — parar o container antes evita
copiar o banco em escrita (mesmo raciocínio do incidente documentado no
[README do any-sync-bundle](../any-sync-bundle/README.md)):

```bash
systemctl --user stop gitea
tar -czf gitea-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes gitea
systemctl --user start gitea
```

Os secrets (`~/.config/containers/secrets/gitea/`) também precisam de
backup separado — sem `SECRET_KEY`/`INTERNAL_TOKEN` originais, senhas de
usuário e tokens de acesso gravados no banco restaurado não conseguem
ser decriptados.

## Comandos úteis

```bash
systemctl --user status gitea
podman logs -f gitea
podman exec gitea gitea admin user list
```

## Créditos

Deploy Quadlet baseado no [Gitea](https://github.com/go-gitea/gitea).
Licença original: MIT.
