# Memos — Podman Quadlet (rootless)

Deploy do [Memos](https://usememos.com) (notas rápidas self-hosted,
markdown-nativo, leve) via Podman Quadlet, usando a imagem oficial
[`neosmemo/memos`](https://github.com/usememos/memos).

## Arquitetura

Container único, roda como root internamente (sem `PUID`/`PGID`, sem
`UserNS=keep-id` — a própria imagem ajusta o dono do volume sozinha no
primeiro start, mesmo padrão de vários outros apps deste repositório).
**SQLite embutido** — um volume só, guarda o banco inteiro
(`/var/opt/memos`).

Healthcheck usa o endpoint próprio da imagem (`/healthz`, testado na
prática) — não precisa de checagem HTTP genérica.

## Arquivos

```
memos-net.network   # rede bridge isolada
memos.container       # unit principal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero

```bash
# 1. Baixar as units (sem precisar clonar o repositório)
mkdir -p ~/.config/containers/systemd/memos
wget -P ~/.config/containers/systemd/memos/ \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/memos/memos-net.network \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/memos/memos.container

# 2. Diretório de dados — bind mount exige que já exista antes do start
mkdir -p ~/.config/containers/volumes/memos/data

# 3. Env não-secreto
mkdir -p ~/.config/containers/env
wget -O ~/.config/containers/env/memos.env \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/memos/.env.example

# 4. Subir
systemctl --user daemon-reload
systemctl --user start memos
```

Acessar `http://<ip-do-host>:5230` (ou via [tsdproxy](../tsdproxy/) em
`https://memos.<seu-tailnet>.ts.net`) e criar a conta no primeiro
acesso — **o primeiro usuário a se cadastrar vira admin
automaticamente**, sem confirmação de e-mail (diferente do
[Monica](../monica/)). Depois de criar essa conta, desligar cadastro
aberto em Configurações → (seção de admin) → "Allow user signup", senão
qualquer um que alcance a URL consegue criar conta própria.

## Auto-update

Sem `AutoUpdate=` — tag explícita (`0.29.1`), bump manual (regra 9 do
README raiz). A imagem tem `wget`/healthcheck real (`/healthz`) — daria
pra habilitar `AutoUpdate=registry` com rollback funcional, mas notas
são dado real do usuário, mesmo raciocínio do
[baikal](../baikal/)/[Mealie](../mealie/) — revisão manual antes de
atualizar.

## Backup & Recuperação

```bash
systemctl --user stop memos
tar -czf memos-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes memos
systemctl --user start memos
```

## Comandos úteis

```bash
systemctl --user status memos
podman logs -f memos
podman exec memos wget -qO- http://127.0.0.1:5230/healthz
```

## Créditos

Deploy Quadlet baseado no [Memos](https://github.com/usememos/memos)
(MIT).
