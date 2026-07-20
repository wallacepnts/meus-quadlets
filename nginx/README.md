# nginx — Podman Quadlet (rootless)

Deploy do [nginx](https://nginx.org) como servidor de arquivos estáticos
via Podman Quadlet, usando a imagem oficial
[`nginx`](https://hub.docker.com/_/nginx) (variante Alpine).

## Arquitetura

Container único. Dois bind mounts, ambos `:ro` de propósito (o nginx só
lê, quem edita é você direto no host):

- `html/` → `/usr/share/nginx/html` — o conteúdo estático em si (o que
  fica montado aqui é o que é servido).
- `conf.d/` → `/etc/nginx/conf.d` — server blocks. **Não pode ficar
  vazio**: montar um diretório vazio por cima de `/etc/nginx/conf.d`
  apaga o `default.conf` embutido da imagem — sem nenhum `server {
  listen 80; }`, o nginx sobe mas não escuta em porta nenhuma
  (`wget: can't connect to remote host` no healthcheck, testado na
  prática). Por isso este repositório versiona uma cópia do
  `default.conf` original da imagem em `conf.d/` — baixado no passo 2 da
  instalação; editar esse arquivo (ou adicionar outros `.conf` do lado)
  pra customizar rotas.

## Arquivos

```
nginx-net.network       # rede bridge isolada
nginx.container         # unit principal

conf.d/
└── default.conf        # cópia do default.conf original da imagem
```

Sem `.env.example` — nada aqui depende de variável de ambiente.

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero

```bash
# 1. Baixar as units (sem precisar clonar o repositório)
mkdir -p ~/.config/containers/systemd/nginx
wget -P ~/.config/containers/systemd/nginx/ \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/nginx/nginx-net.network \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/nginx/nginx.container

# 2. Diretórios de dados — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/nginx/{html,conf.d}
echo "<h1>Funcionando</h1>" > ~/.config/containers/volumes/nginx/html/index.html
wget -O ~/.config/containers/volumes/nginx/conf.d/default.conf \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/nginx/conf.d/default.conf

# 3. Subir
systemctl --user daemon-reload
systemctl --user start nginx
```

Acessar em `http://<ip-do-host>:8086`, ou via [tsdproxy](../tsdproxy/)
(tailnet) em `https://nginx.<seu-tailnet>.ts.net`.

## Auto-update

Sem `AutoUpdate=` — tag explícita (`1.30.4-alpine`, atual `stable`),
bump manual (regra 9 do README raiz). A imagem tem `wget`/healthcheck
real — daria pra habilitar `AutoUpdate=registry` com rollback de
verdade, mas mantido manual por padrão como o resto do repositório.

## Backup & Recuperação

```bash
tar -czf nginx-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes nginx
```

Sem precisar parar o container (leitura só, sem estado próprio além do
conteúdo estático).

## Comandos úteis

```bash
systemctl --user status nginx
podman logs -f nginx
podman exec nginx wget -qO- http://127.0.0.1:80/
```

## Créditos

Deploy Quadlet usando a imagem oficial [nginx](https://hub.docker.com/_/nginx)
(BSD-2-Clause).
