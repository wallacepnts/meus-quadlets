# Mealie — Podman Quadlet (rootless)

Deploy do [Mealie](https://mealie.io) (gerenciador de receitas,
planejamento de refeições e lista de compras self-hosted) via Podman
Quadlet, usando a imagem oficial
[`ghcr.io/mealie-recipes/mealie`](https://docs.mealie.io/documentation/getting-started/installation/docker/).

## Arquitetura

Container único. **SQLite embutido** — o próprio projeto recomenda como
padrão pra até ~20 usuários (documentado explicitamente: "SQLite is
not designed to be used with Network Attached Storage", ou seja, só
não usar se o volume de dados morar em NFS/SMB — não é o caso aqui,
bind mount local). Sem `UserNS=keep-id` — a imagem faz `usermod`
interno com `PUID`/`PGID` (mesmo mecanismo LinuxServer.io-like já usado
em outros apps deste repositório).

Suporta **OIDC nativo** (`enableOidc` na config) — dá pra integrar com o
[Authentik](../authentik/) deste repositório do mesmo jeito que o
[Karakeep](../karakeep/), se quiser SSO em vez de login local (fora do
escopo desta instalação inicial).

## Arquivos

```
mealie-net.network   # rede bridge isolada
mealie.container       # unit principal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero

```bash
# 1. Baixar as units (sem precisar clonar o repositório)
mkdir -p ~/.config/containers/systemd/mealie
wget -P ~/.config/containers/systemd/mealie/ \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/mealie/mealie-net.network \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/mealie/mealie.container

# 2. Diretório de dados — bind mount exige que já exista antes do start
mkdir -p ~/.config/containers/volumes/mealie/data

# 3. Env não-secreto — baixar o exemplo, ajustar PUID/PGID/TZ/BASE_URL
mkdir -p ~/.config/containers/env
wget -O ~/.config/containers/env/mealie.env \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/mealie/.env.example
sed -i "s/^PUID=.*/PUID=$(id -u)/;s/^PGID=.*/PGID=$(id -g)/" \
  ~/.config/containers/env/mealie.env

# 4. Subir
systemctl --user daemon-reload
systemctl --user start mealie
```

Acessar `http://<ip-do-host>:9091` (ou via [tsdproxy](../tsdproxy/) em
`https://mealie.<seu-tailnet>.ts.net`).

## Trocar a senha padrão (obrigatório logo no primeiro acesso)

**A imagem sobe com uma conta admin padrão e senha conhecida** — sem
trocar, qualquer um que alcance a URL tem acesso total:

```
E-mail: changeme@example.com
Senha:  MyPassword
```

Logar com essas credenciais e trocar em Perfil → Senha imediatamente.

## Auto-update

Sem `AutoUpdate=` — tag explícita (`v3.20.1`), bump manual (regra 9 do
README raiz). A imagem tem `curl`/healthcheck real (endpoint próprio
`/api/app/about`, testado na prática) — daria pra habilitar
`AutoUpdate=registry` com rollback funcional, mas receitas/planejamento
são dado real do usuário — revisão manual antes de atualizar, mesmo
raciocínio do [baikal](../baikal/)/[Radicale](../radicale/).

## Backup & Recuperação

```bash
systemctl --user stop mealie
tar -czf mealie-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes mealie
systemctl --user start mealie
```

`data/` inclui o banco SQLite, imagens de receitas/perfis e os backups
que o próprio Mealie gera pela UI (Configurações → Backup) — redundante
com este `tar`, mas útil se quiser restaurar só pela interface em vez
de mexer no volume direto.

## Comandos úteis

```bash
systemctl --user status mealie
podman logs -f mealie
podman exec mealie curl -fsS http://127.0.0.1:9000/api/app/about
```

## Créditos

Deploy Quadlet baseado no [Mealie](https://github.com/mealie-recipes/mealie)
(AGPL-3.0).
