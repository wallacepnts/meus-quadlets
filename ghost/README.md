# Ghost — Podman Quadlet (rootless)

Deploy do [Ghost](https://ghost.org) (plataforma de blog/newsletter
self-hosted) via Podman Quadlet, usando a imagem oficial
[`ghost`](https://hub.docker.com/_/ghost) (variante Alpine).

## SQLite em modo development — decisão consciente

O Ghost **só suporta SQLite oficialmente em modo `development`**
(`NODE_ENV=development`) — produção de verdade, pelo próprio projeto,
exige MySQL. Mesmo trade-off já aceito pro [ownCloud](../owncloud/)
neste repositório: um container só, mais simples, fora do que o
projeto recomenda oficialmente, mas funcional pra uso pessoal/baixo
volume. Se precisar do caminho "oficial" depois, trocar pra MySQL é só
adicionar um container de banco e trocar as três variáveis
`database__*` (ver [documentação oficial](https://docs.ghost.org/install/docker)).

## Arquitetura

Container único, roda como root internamente (sem `PUID`/`PGID`, sem
`UserNS=keep-id` — a própria imagem ajusta permissão sozinha, mesmo
padrão de vários outros apps deste repositório). Um volume só
(`/var/lib/ghost/content`) — guarda o banco SQLite, imagens/temas
enviados, e configuração.

Healthcheck usa o endpoint de site da própria API admin do Ghost
(`/ghost/api/admin/site/`, sem autenticação, leve) — testado na
prática, mais barato que buscar a home inteira.

**Ruído esperado no log**: o Ghost tenta calcular o tamanho do próprio
favicon buscando a `url` configurada — se essa URL não resolver de
volta pro próprio container (comum atrás de proxy/tailnet, testado na
prática), aparece um erro `ECONNREFUSED`/`IMAGE_SIZE_URL` no log.
Cosmético, não impede o site de funcionar.

## Arquivos

```
ghost-net.network   # rede bridge isolada
ghost.container       # unit principal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero

```bash
# 1. Baixar as units (sem precisar clonar o repositório)
mkdir -p ~/.config/containers/systemd/ghost
wget -P ~/.config/containers/systemd/ghost/ \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/ghost/ghost-net.network \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/ghost/ghost.container

# 2. Diretório de dados — bind mount exige que já exista antes do start
mkdir -p ~/.config/containers/volumes/ghost/content

# 3. Env não-secreto — baixar o exemplo e EDITAR a url pro domínio real
#    antes de subir (mesmo motivo do Monica: deixar o placeholder gera
#    link/e-mail quebrado)
mkdir -p ~/.config/containers/env
wget -O ~/.config/containers/env/ghost.env \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/ghost/.env.example

# 4. Subir
systemctl --user daemon-reload
systemctl --user start ghost
```

Acessar `http://<ip-do-host>:9094/ghost/` (ou via
[tsdproxy](../tsdproxy/) em
`https://ghost.<seu-tailnet>.ts.net/ghost/`) e criar a conta admin no
assistente de instalação do primeiro acesso.

## Auto-update

Sem `AutoUpdate=` — tag explícita (`6.53.0-alpine`), bump manual (regra
9 do README raiz). A imagem tem `wget`/healthcheck real — daria pra
habilitar `AutoUpdate=registry` com rollback funcional, mas
posts/config são dado real do usuário, revisão manual antes de
atualizar. Migrações de schema entre versões maiores do Ghost também
não são raras — checar o changelog antes de trocar de tag.

## Backup & Recuperação

```bash
systemctl --user stop ghost
tar -czf ghost-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes ghost
systemctl --user start ghost
```

## Comandos úteis

```bash
systemctl --user status ghost
podman logs -f ghost
podman exec ghost wget -qO- http://127.0.0.1:2368/ghost/api/admin/site/
```

## Créditos

Deploy Quadlet baseado no [Ghost](https://github.com/TryGhost/Ghost)
(MIT).
