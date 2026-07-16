# Vaultwarden — Podman Quadlet (rootless)

Deploy do [Vaultwarden](https://github.com/dani-garcia/vaultwarden)
(implementação alternativa, em Rust, do servidor Bitwarden) via Podman
Quadlet. Cofre de senhas self-hosted — compatível com os apps oficiais do
Bitwarden (basta trocar o "server URL" nas configurações do app).

## Arquitetura

Container único, SQLite embutido (`/data/db.sqlite3`) — sem serviço de
banco separado, ao contrário do [linkwarden](../linkwarden/). Expõe `80`
internamente (mapeado pra `8082` no host).

## Arquivos

```
quadlet/
└── vaultwarden.container   # unit principal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando
- `python3` com o pacote `argon2-cffi` (`pip3 install --user argon2-cffi`)
  — só pra gerar o `ADMIN_TOKEN` com hash seguro no passo de instalação

## Instalação do zero

```bash
# 1. Copiar a unit
mkdir -p ~/.config/containers/systemd
cp quadlet/vaultwarden.container ~/.config/containers/systemd/

# 2. Diretório de dados — bind mount exige que já exista antes do start
mkdir -p ~/.config/containers/volumes/vaultwarden/data

# 3. ADMIN_TOKEN como hash Argon2id (não texto puro) — é a forma
#    recomendada pelo próprio projeto. O comando oficial `vaultwarden
#    hash` exige TTY interativo (não dá pra automatizar em script), então
#    geramos o hash equivalente em Python com os MESMOS parâmetros do
#    preset "bitwarden" que o binário usa (m=65540, t=3, p=4).
mkdir -p ~/.config/containers/secrets/vaultwarden
python3 - <<'PYEOF'
from argon2 import PasswordHasher
from argon2.low_level import Type
import secrets
import os

secrets_dir = os.path.expanduser("~/.config/containers/secrets/vaultwarden")
ph = PasswordHasher(time_cost=3, memory_cost=65540, parallelism=4, hash_len=32, salt_len=16, type=Type.ID)
raw_secret = secrets.token_urlsafe(32)
phc = ph.hash(raw_secret)

with open(f"{secrets_dir}/admin-token-raw.txt", "w") as f:
    f.write(raw_secret)
with open(f"{secrets_dir}/admin-token-hash.txt", "w") as f:
    f.write(phc)

print("Token admin (guardar em local seguro, é a SENHA do painel /admin):")
print(raw_secret)
PYEOF
chmod 600 ~/.config/containers/secrets/vaultwarden/*.txt

podman secret create vaultwarden-admin-token ~/.config/containers/secrets/vaultwarden/admin-token-hash.txt

# 4. Env não-secreto
mkdir -p ~/.config/containers/env
cat > ~/.config/containers/env/vaultwarden.env <<'EOF'
# Domínio real de acesso — usado pra gerar URLs de anexo, WebAuthn/passkey
# etc. corretamente. Trocar pro endereço da tailnet ou local conforme uso.
DOMAIN=https://vaultwarden.<seu-tailnet>.ts.net
# Deixar "true" só até criar a primeira conta — depois, trocar pra
# "false" (ver seção Segurança abaixo).
SIGNUPS_ALLOWED=true
ENABLE_WEBSOCKET=true
EOF

# 5. Subir
systemctl --user daemon-reload
systemctl --user start vaultwarden
```

Acessar via [tsdproxy](../tsdproxy/) (tailnet) em
`https://vaultwarden.<seu-tailnet>.ts.net`, ou local em
`http://localhost:8082`. Criar a primeira conta, depois seguir a seção
Segurança abaixo.

**O valor impresso em "Token admin"** (a string crua, não o hash) é a
senha do painel `/admin` — guardar em local seguro (ex.: no próprio
Vaultwarden depois de criado, ironicamente, ou em outro gerenciador). O
que fica salvo em `admin-token-hash.txt` é só o hash Argon2id — não dá
pra recuperar a senha original a partir dele.

## Segurança

- **Desabilitar cadastro depois da primeira conta**: `SIGNUPS_ALLOWED=false`
  em `vaultwarden.env`, `systemctl --user restart vaultwarden`.
  Sem isso, qualquer um que alcançar a URL consegue criar conta própria.
- **`ADMIN_TOKEN` como hash, não texto puro** — já é o padrão deste setup
  (ver passo 3). Um `ADMIN_TOKEN` em texto puro no arquivo de secret, se
  vazar, dá acesso total ao painel admin (todos os usuários, organizações,
  configuração do servidor). O hash Argon2id não é reversível.
- **Nunca publicar o painel `/admin` fora da tailnet** — só o app cliente
  (login normal) precisa ser alcançável de fora; o admin é coisa sua.

## Auto-update

Sem `AutoUpdate=` — tag explícita (`1.36.0-alpine`), bump manual (regra 9
do README raiz). A imagem tem `wget`/`curl` (Alpine), então dá pra ligar
auto-update com rollback de verdade se decidir habilitar — mas pra um
cofre de senhas, atualização manual revisada antes é o padrão recomendado
aqui.

## Backup & Recuperação

Tudo fica em `volumes/vaultwarden/data/` (SQLite + anexos + ícones em
cache). É o dado mais sensível deste repositório inteiro — parar antes de
copiar:

```bash
systemctl --user stop vaultwarden
tar -czf vaultwarden-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes vaultwarden
systemctl --user start vaultwarden
```

O `admin-token-raw.txt` (a senha do painel admin) também precisa de
backup separado — não tem como recuperar se perder, só resetar criando um
`ADMIN_TOKEN` novo.

## Comandos úteis

```bash
systemctl --user status vaultwarden
podman logs -f vaultwarden
curl http://127.0.0.1:8082/alive
```

## Créditos

Deploy Quadlet baseado no [Vaultwarden](https://github.com/dani-garcia/vaultwarden),
de [Daniel García (@dani-garcia)](https://github.com/dani-garcia).
Licença original: AGPL-3.0.
