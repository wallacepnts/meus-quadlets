# Beszel — Podman Quadlet (rootless)

Deploy do [Beszel](https://beszel.dev) (dashboard leve de monitoramento
de recursos — CPU, RAM, disco, rede, containers — com histórico e
alertas) via Podman Quadlet, seguindo o
[guia oficial](https://www.beszel.dev/guide/getting-started) e a
variante ["same-system"](https://github.com/henrygd/beszel/tree/main/supplemental/docker/same-system)
(hub e agent monitorando o mesmo host).

## Arquitetura

Arquitetura hub + agent, dois containers:

- **`beszel`** (hub) — painel web + banco de dados (SQLite/PocketBase),
  porta `8090`, rede bridge própria (`beszel-net`).
- **`beszel-agent`** — coleta as métricas deste host e reporta pro hub.
  **Rede `host`, não bridge** (foge do padrão deste repositório de
  propósito): o agent reporta o tráfego real das interfaces do host;
  numa rede bridge isolada, só enxergaria o veth interno do próprio
  container — números inúteis pra monitoramento de rede.

**Hub e agent no mesmo host conectam via socket Unix compartilhado**
(`beszel_socket`, bind mount comum aos dois), não por TCP com token
exposto na rede — mais simples e mais seguro que a variante
multi-host padrão (usada quando o agent roda em *outra* máquina, fora do
escopo deste repositório).

**Monitoramento de containers**: o agent lê o socket do Podman
(`%t/podman/podman.sock`, exposto como `/var/run/docker.sock` — API
compatível com Docker) pra listar/monitorar os outros containers deste
host, mesmo mecanismo do [tsdproxy](../tsdproxy/).

**Imagens sem shell** (binário estático só, `/beszel`/`/agent`) —
`HealthCmd` usa `CMD`, não `CMD-SHELL` (testado na prática: `CMD-SHELL`
falha por não achar `/bin/sh`); os próprios binários têm um subcomando
`health` feito pra isso.

## Arquivos

```
beszel-net.network       # rede do hub
beszel.container          # hub — painel + banco
beszel-agent.container    # agent — coleta métricas deste host
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando
- `podman.socket` habilitado (mesmo pré-requisito do
  [tsdproxy](../tsdproxy/) — `systemctl --user enable --now podman.socket`
  se ainda não estiver)
- `ssh-keygen` no host (só pro passo 5 abaixo, pra ler a chave pública do
  hub direto do arquivo, sem precisar copiar pela UI)

## Instalação do zero

```bash
# 1. Baixar as units (sem precisar clonar o repositório)
mkdir -p ~/.config/containers/systemd/beszel
wget -P ~/.config/containers/systemd/beszel/ \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/beszel/beszel-net.network \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/beszel/beszel.container \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/beszel/beszel-agent.container

# 2. Diretórios de dados — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/beszel/{hub-data,socket,agent-data}

# 3. Env — baixar o exemplo, ajustar APP_URL pra URL real de acesso
mkdir -p ~/.config/containers/env
wget -O ~/.config/containers/env/beszel.env \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/beszel/.env.example
# editar APP_URL no arquivo baixado — valor de exemplo com "<seu-tailnet>"
# literal não sobe (hub recusa com "appURL: must be a valid URL"),
# testado na prática; usar a URL real (tsdproxy) ou http://localhost:8090

# 4. Subir só o hub primeiro
systemctl --user start beszel
```

Acessar `http://<ip-do-host>:8090` (ou via [tsdproxy](../tsdproxy/) em
`https://beszel.<seu-tailnet>.ts.net`) e criar a conta de admin no
primeiro acesso.

```bash
# 5. KEY — chave pública do hub, a mesma pra qualquer agent deste hub;
#    lida direto do arquivo (sem precisar copiar pela UI)
mkdir -p ~/.config/containers/secrets/beszel
ssh-keygen -y -f ~/.config/containers/volumes/beszel/hub-data/id_ed25519 \
  > ~/.config/containers/secrets/beszel/key.txt
chmod 600 ~/.config/containers/secrets/beszel/key.txt
podman secret create beszel-agent-key ~/.config/containers/secrets/beszel/key.txt

# 6. TOKEN — esse já precisa vir da UI: painel do hub → "Add System"
#    (ou Configurações → Tokens) → copiar o token mostrado
read -s -p "Token do Beszel: " BESZEL_TOKEN; echo
echo -n "$BESZEL_TOKEN" > ~/.config/containers/secrets/beszel/token.txt
unset BESZEL_TOKEN
chmod 600 ~/.config/containers/secrets/beszel/token.txt
podman secret create beszel-agent-token ~/.config/containers/secrets/beszel/token.txt

# 7. Subir o agent
systemctl --user daemon-reload
systemctl --user start beszel-agent
```

O sistema aparece no painel do hub como "online" assim que o agent
conectar pelo socket compartilhado.

## Monitorar discos/partições extras

Bind mount adicional em `/extra-filesystems/<nome>` no
`beszel-agent.container`:

```ini
Volume=/mnt/disco1:/extra-filesystems/disco1:ro
```

## Auto-update

Sem `AutoUpdate=` nos dois — tags explícitas (`0.18.7`), bump manual
(regra 9 do README raiz). Ambas as imagens têm healthcheck real
(`/beszel health`/`/agent health`, testados na prática) — daria pra
habilitar `AutoUpdate=registry` com rollback funcional, mas mantido
manual como padrão do repositório.

## Backup & Recuperação

```bash
systemctl --user stop beszel-agent beszel
tar -czf beszel-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes beszel
systemctl --user start beszel beszel-agent
```

`hub-data/id_ed25519` está incluído no backup — restaurar preserva a
mesma KEY, os agents continuam autenticando sem reconfigurar.

## Comandos úteis

```bash
systemctl --user status beszel beszel-agent
podman logs -f beszel
podman logs -f beszel-agent
podman exec beszel /beszel health --url http://localhost:8090
podman exec beszel-agent /agent health
```

## Créditos

Deploy Quadlet baseado no [Beszel](https://github.com/henrygd/beszel)
(MIT).
