# Wingfit — Podman Quadlet (rootless)

Deploy do [Wingfit](https://github.com/itskovacs/Wingfit) (planejamento
e acompanhamento de treinos, self-hosted) via Podman Quadlet, usando a
imagem oficial `ghcr.io/itskovacs/wingfit`.

## Arquitetura

Container único (FastAPI + SQLite embutido) — um volume só
(`/app/storage`), guarda banco, logs e assets enviados.

**Configuração opcional via `storage/config.yml`**, não variável de
ambiente — diferente da maioria dos apps deste repositório. O arquivo
não vem por padrão (a imagem funciona sem ele, com os defaults); só
criar se quiser mudar algo (ver seção "Configuração opcional" abaixo).

Healthcheck usa `python3` embutido pra testar HTTP — a imagem **não
tem `wget`/`curl`** (base Python slim, testado na prática).

## Arquivos

```
wingfit-net.network   # rede bridge isolada
wingfit.container       # unit principal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero

```bash
# 1. Baixar as units (sem precisar clonar o repositório)
mkdir -p ~/.config/containers/systemd/wingfit
wget -P ~/.config/containers/systemd/wingfit/ \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/wingfit/wingfit-net.network \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/wingfit/wingfit.container

# 2. Diretório de dados — bind mount exige que já exista antes do start
mkdir -p ~/.config/containers/volumes/wingfit/storage

# 3. Ícone customizado — Wingfit não tem equivalente no dashboard-icons
#    usado pelo homepage deste repositório, copiar o ícone oficial do
#    próprio projeto (ver README do homepage, seção sobre ícone
#    customizado)
mkdir -p ~/.config/containers/volumes/homepage/icons
wget -O ~/.config/containers/volumes/homepage/icons/wingfit.png \
  https://raw.githubusercontent.com/itskovacs/Wingfit/main/src/public/favicon_square.png
systemctl --user restart homepage   # só detecta ícone novo depois de reiniciar

# 4. Subir
systemctl --user daemon-reload
systemctl --user start wingfit
```

Acessar `http://<ip-do-host>:8093` (ou via [tsdproxy](../tsdproxy/) em
`https://wingfit.<seu-tailnet>.ts.net`) e criar a conta em `/register`
no primeiro acesso.

## Configuração opcional

Editar `~/.config/containers/volumes/wingfit/storage/config.yml`
(criar se não existir) e reiniciar o container depois de qualquer
mudança:

```yaml
# Duração dos tokens (minutos)
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_MINUTES=1440

# Desligar cadastro aberto (fazer depois de criar sua conta)
REGISTER_ENABLE=false

# OIDC — integrar com um provedor externo (ex.: Authentik deste repo)
OIDC_DISCOVERY_URL="https://authentik.<seu-tailnet>.ts.net/application/o/<slug>/.well-known/openid-configuration"
OIDC_CLIENT_ID="..."
OIDC_CLIENT_SECRET="..."
OIDC_REDIRECT_URI="https://wingfit.<seu-tailnet>.ts.net/auth"
```

```bash
systemctl --user restart wingfit
```

## Auto-update

Sem `AutoUpdate=` — tag explícita (`5.3.1`), bump manual (regra 9 do
README raiz). Sem `HealthCmd` baseado em `curl`/`wget` tradicional (a
imagem não tem nenhum dos dois), mas o healthcheck via `python3` é um
teste HTTP real — daria pra habilitar `AutoUpdate=registry` com
rollback funcional, mas treinos/progresso são dado real do usuário,
revisão manual antes de atualizar.

## Backup & Recuperação

```bash
systemctl --user stop wingfit
tar -czf wingfit-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes wingfit
systemctl --user start wingfit
```

## Comandos úteis

```bash
systemctl --user status wingfit
podman logs -f wingfit
podman exec wingfit python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/').status)"
```

## Créditos

Deploy Quadlet baseado no [Wingfit](https://github.com/itskovacs/Wingfit)
(CC BY-NC-SA 4.0).
