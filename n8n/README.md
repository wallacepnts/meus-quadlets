# n8n — Podman Quadlet (rootless)

Deploy do [n8n](https://n8n.io) (automação de workflows via editor visual
de nós — tipo um Zapier/IFTTT self-hosted) via Podman Quadlet, seguindo o
[guia oficial de instalação com Docker](https://docs.n8n.io/deploy/host-n8n/install-options/install-with-docker/).

## Arquitetura

Container único, banco **SQLite embutido** em `/home/node/.n8n` (default
oficial — dá pra trocar por Postgres depois, ver seção Variantes, mas não
é o setup daqui). Modo single-instance, sem fila (Redis) — suficiente pra
uso pessoal; modo fila é só necessário em escala (muitos workflows
concorrentes).

A imagem roda como usuário fixo `node`, sem usermod interno (mesmo caso
do Jellyfin/Seerr no [media-stack](../media-stack/)) — por isso
`UserNS=keep-id` no `.container`, mapeando o container pro mesmo uid do
usuário que roda o Podman. Sem isso, o container não é dono do bind
mount criado pelo host (ver Solução de problemas).

## Arquivos

```
n8n.container   # unit principal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando
- `openssl` (pra gerar o secret)

## Instalação do zero

```bash
# 1. Copiar a unit
mkdir -p ~/.config/containers/systemd
cp n8n.container ~/.config/containers/systemd/

# 2. Diretório de dados — bind mount exige que já exista antes do start
mkdir -p ~/.config/containers/volumes/n8n/data

# 3. Secret — chave de criptografia das credenciais salvas nos workflows
#    (tokens de API, senhas etc.). Gerar explícito em vez de deixar o
#    n8n gerar sozinho no primeiro start, pra ter o valor documentado.
mkdir -p ~/.config/containers/secrets/n8n
openssl rand -hex 32 | tr -d '\n' > ~/.config/containers/secrets/n8n/encryption-key.txt
chmod 600 ~/.config/containers/secrets/n8n/encryption-key.txt
podman secret create n8n-encryption-key ~/.config/containers/secrets/n8n/encryption-key.txt

# 4. Env não-secreto — copiar o exemplo
mkdir -p ~/.config/containers/env
cp .env.example ~/.config/containers/env/n8n.env

# 5. Subir
systemctl --user daemon-reload
systemctl --user start n8n
```

Acessar via [tsdproxy](../tsdproxy/) (tailnet) em
`https://n8n.<seu-tailnet>.ts.net`, ou local em `http://localhost:5678`.
Criar a primeira conta pela própria UI (sem usuário/senha padrão).

**Se for usar webhooks de produção** chamados por serviços de fora deste
host, definir `WEBHOOK_URL` em `n8n.env` com o endereço público/tailnet
— sem isso, o n8n usa o endereço local, que não é alcançável de fora.

## Auto-update

Sem `AutoUpdate=` — tag explícita (`1.123.66`), bump manual (regra 9 do
README raiz). A imagem tem `wget`/healthcheck real (daria pra habilitar
com rollback de verdade), mas os workflows/credenciais salvos são dado
real do usuário — revisão manual antes de atualizar, mesmo raciocínio do
baikal/vaultwarden.

## Backup & Recuperação

```bash
systemctl --user stop n8n
tar -czf n8n-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes n8n
systemctl --user start n8n
```

O secret (`~/.config/containers/secrets/n8n/`) também precisa de backup
separado — sem a mesma `N8N_ENCRYPTION_KEY`, as credenciais salvas nos
workflows (tokens, senhas de outros serviços) ficam ilegíveis ao
restaurar num host novo.

## Variantes

O guia oficial também documenta trocar SQLite por Postgres
(`DB_TYPE=postgresdb` + `DB_POSTGRESDB_*`) — não usado aqui de propósito,
mesmo raciocínio do baikal/paperless-ngx: evitar mais um banco externo
sem necessidade real pro volume de uso esperado.

## Solução de problemas

**`toomanyrequests: You have reached your unauthenticated pull rate
limit`** ao puxar a imagem — testado na prática: o guia oficial recomenda
`docker.n8n.io/n8nio/n8n`, mas esse mirror bate no rate limit anônimo do
Docker Hub por trás dele. Fazer `podman login docker.io` **não resolve**,
porque é um registro separado — a autenticação não se propaga pro
mirror. Solução: usar `docker.io/n8nio/n8n` direto (mesma imagem, mesma
tag), onde a autenticação funciona de verdade. Já é o que este
`.container` usa.

**`Error: EACCES: permission denied, open '/home/node/.n8n/config'`** no
primeiro start — a imagem roda como usuário fixo `node` (uid interno
fixo, sem usermod tipo LSIO). Sem `UserNS=keep-id`, o bind mount criado
pelo host (`mkdir -p`, dono = seu uid) não é acessível pro uid do `node`
dentro do container. `UserNS=keep-id` resolve, mapeando o container pro
mesmo uid de quem roda o Podman — já incluído no `.container` deste
repositório, só documentando caso apareça de novo em outro host.

## Comandos úteis

```bash
systemctl --user status n8n
podman logs -f n8n
podman exec n8n wget -qO- http://127.0.0.1:5678/healthz
```

## Créditos

Deploy Quadlet baseado no [n8n](https://github.com/n8n-io/n8n).
Licença original: Sustainable Use License (fair-code, não é open source
puro — uso próprio/interno é livre, revender o software hospedado por
terceiros não).
