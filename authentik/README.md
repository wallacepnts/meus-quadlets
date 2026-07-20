# Authentik — Podman Quadlet (rootless)

Deploy do [Authentik](https://goauthentik.io) (servidor de identidade —
SSO, MFA, OIDC/SAML) via Podman Quadlet, seguindo o
[`compose.yml`](https://docs.goauthentik.io/compose.yml) oficial.

**Implantado só pra teste/exploração** — ver "Limitação importante"
abaixo antes de esperar que ele proteja outros apps deste repositório
sozinho.

## Limitação importante: sem forward-auth automático aqui

O uso mais comum do Authentik é na frente de outros apps, exigindo login
antes de liberar acesso (SSO — um login só, protege tudo atrás do
proxy). Isso normalmente depende do proxy da frente saber conversar com
o Authentik (**forward-auth**, mesmo mecanismo do Authelia) — o
[tsdproxy](../tsdproxy/) (proxy usado neste repositório) **não suporta
isso**, testado/pesquisado antes de decidir implantar.

O Authentik tem uma saída que o Authelia não tem: **outposts em "Proxy
Mode"** — um container extra por app protegido, que funciona como
reverse proxy completo (recebe a requisição, confere login, só então
repassa pro app de verdade) — nesse modo, dá pra apontar o tsdproxy pro
outpost em vez de apontar direto pro app, sem precisar de forward-auth
em lugar nenhum. **Não implantado ainda** — fica documentado aqui como
o próximo passo, app por app, se/quando fizer sentido usar de verdade
(cada app protegido = mais um outpost container).

Por enquanto, este deploy é só o **core** (portal + admin) — dá pra
explorar a interface, criar usuários/grupos, configurar provedores
OIDC/SAML, sem nenhum outro serviço deste repositório depender dele.

## Arquitetura

Três containers na rede `authentik-net.network`:

- `authentik-postgres` — banco (Postgres puro, **sem opção SQLite** —
  diferente da maioria dos apps deste repositório, é exigência do
  próprio Authentik).
- `authentik` — o server (porta `9000` HTTP / `9443` HTTPS, só a `9000`
  publicada — TLS já é feito pelo tsdproxy na borda da tailnet).
- `authentik-worker` — tarefas em segundo plano (envio de e-mail,
  outposts, outras tarefas assíncronas) — roda como **root dentro do
  container** (`User=0`, igual ao compose oficial) e tem acesso ao
  socket do Podman, necessário só quando outposts entrarem em uso.

`authentik`/`authentik-worker` sobem só depois que o Postgres reporta
`healthy` (`Requires=`/`After=`, mesmo padrão do
[linkwarden](../linkwarden/)/[immich](../immich/)).

**Sem `AUTHENTIK_REDIS__*`** — versões recentes do Authentik não exigem
mais Redis (confirmado no `compose.yml` oficial atual, que só tem
`postgresql`+`server`+`worker`) — arquitetura mais enxuta do que guias
antigos sugerem.

## Arquivos

```
authentik-net.network         # rede dedicada
authentik-postgres.container  # banco
authentik.container            # server (portal + admin)
authentik-worker.container     # tarefas em segundo plano
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando
- `podman.socket` habilitado (só pro worker — `systemctl --user enable
  --now podman.socket` se ainda não estiver, mesmo pré-requisito do
  [tsdproxy](../tsdproxy/)/[Beszel](../beszel/))

## Instalação do zero

```bash
# 1. Baixar as units (sem precisar clonar o repositório)
mkdir -p ~/.config/containers/systemd/authentik
wget -P ~/.config/containers/systemd/authentik/ \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/authentik/authentik-net.network \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/authentik/authentik-postgres.container \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/authentik/authentik.container \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/authentik/authentik-worker.container

# 2. Diretórios de dados — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/authentik/{postgres,data,certs}

# 3. Secrets — senha do Postgres + chave de assinatura do Authentik.
#    IMPORTANTE: sem newline no arquivo (`print(..., end='')`, não
#    `print(...)` puro) — testado na prática, o Postgres tolera o
#    newline sobrando na senha (o script de init dele descarta), mas o
#    Authentik não: a autenticação falha em loop
#    ("password authentication failed") com a MESMA senha, só porque um
#    lado compara a string com \n no final e o outro sem.
mkdir -p ~/.config/containers/secrets/authentik
python3 -c "import secrets; print(secrets.token_urlsafe(32), end='')" \
  > ~/.config/containers/secrets/authentik/postgres-password.txt
python3 -c "import secrets; print(secrets.token_urlsafe(48), end='')" \
  > ~/.config/containers/secrets/authentik/secret-key.txt
chmod 600 ~/.config/containers/secrets/authentik/*.txt
podman secret create authentik-postgres-password \
  ~/.config/containers/secrets/authentik/postgres-password.txt
podman secret create authentik-secret-key \
  ~/.config/containers/secrets/authentik/secret-key.txt

# 4. Subir (o server já sobe o Postgres sozinho via Requires=)
systemctl --user daemon-reload
systemctl --user start authentik
systemctl --user start authentik-worker
```

Acessar `http://<ip-do-host>:9000` (ou via [tsdproxy](../tsdproxy/) em
`https://authentik.<seu-tailnet>.ts.net`) — redireciona pra `/setup` no
primeiro acesso, cria a conta de admin ali (chamada de `akadmin` por
padrão).

## Auto-update

Sem `AutoUpdate=` nos três — tags explícitas (`2026.5.5`), bump manual
(regra 9 do README raiz). Sem `HealthCmd` no Postgres/worker seguindo o
padrão de dependência interna do resto do repositório; o `authentik`
(server) tem `HealthCmd` real (`/-/health/live/`) — daria pra habilitar
rollback funcional nele, mas usuários/grupos/config são dado real,
revisão manual antes de atualizar.

## Backup & Recuperação

```bash
systemctl --user stop authentik authentik-worker authentik-postgres
tar -czf authentik-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes authentik
systemctl --user start authentik-postgres authentik authentik-worker
```

`~/.config/containers/secrets/authentik/` (senha do Postgres + chave de
assinatura) também precisa de backup separado — sem a `secret-key`,
sessões/tokens existentes ficam inválidos mesmo restaurando o banco.

## Comandos úteis

```bash
systemctl --user status authentik-postgres authentik authentik-worker
podman logs -f authentik
podman logs -f authentik-worker
podman exec authentik curl -fsS http://127.0.0.1:9000/-/health/live/
```

## Créditos

Deploy Quadlet baseado no [Authentik](https://github.com/goauthentik/authentik)
(MIT, com módulos enterprise sob licença própria).
