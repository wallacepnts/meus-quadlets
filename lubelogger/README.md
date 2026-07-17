# LubeLogger — Podman Quadlet (rootless)

Deploy do [LubeLogger](https://lubelogger.com) (controle de manutenção
veicular self-hosted) via Podman Quadlet, migrado do `docker-compose.yml`
oficial.

## Arquitetura

Container único, banco embutido por padrão (sem Postgres — dá pra
configurar via `POSTGRES_CONNECTION` se quiser, não usado aqui). Expõe
`8080` internamente (mapeado pra `8083` no host — `8080`/`8082` já usados
por [tsdproxy](../tsdproxy/)/[vaultwarden](../vaultwarden/) neste
repositório).

Dois volumes, como no compose oficial:
- `/App/data` — dados da aplicação
- `/root/.aspnet/DataProtection-Keys` — chaves de criptografia do
  ASP.NET (cookies/sessão); perder isso invalida sessões ativas, não é
  destrutivo pros dados, mas evita regenerar sem necessidade

## Arquivos

```
quadlet/
└── lubelogger.container   # unit principal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero

```bash
# 1. Copiar a unit
mkdir -p ~/.config/containers/systemd
cp quadlet/lubelogger.container ~/.config/containers/systemd/

# 2. Diretórios de dados — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/lubelogger/{data,keys}

# 3. Env — copiar o exemplo e editar o domínio
mkdir -p ~/.config/containers/env
cp .env.example ~/.config/containers/env/lubelogger.env
# editar ~/.config/containers/env/lubelogger.env: LUBELOGGER_DOMAIN

# 4. Subir
systemctl --user daemon-reload
systemctl --user start lubelogger
```

Acessar via [tsdproxy](../tsdproxy/) (tailnet) em
`https://lubelogger.<seu-tailnet>.ts.net`, ou local em
`http://localhost:8083`.

## Segurança — habilitar autenticação é manual, e não é automático

**Por padrão, o LubeLogger não exige login nenhum** — qualquer um que
alcançar a URL tem acesso total de leitura/escrita, sem senha. A própria
documentação confirma: "LubeLogger does not require authentication by
default".

Existe uma forma de pré-configurar isso via env vars
(`EnableAuth`/`UserNameHash`/`UserPasswordHash`, hash SHA256 do usuário e
senha), mas a própria doc marca esse método como não mais recomendado, e
SHA256 sem salt/iterações é um hash fraco pra senha — **não usei essa
abordagem aqui**. O caminho oficial e mais seguro é pela própria interface:

1. Acessar a instância pela primeira vez
2. Ir em **Settings → Enable Authentication**
3. Definir usuário e senha do Root/Super User na hora

**Fazer isso imediatamente após o primeiro start**, antes de cadastrar
qualquer dado real — mesmo estando só na tailnet (não exposto à internet
pública), "só" significa "qualquer dispositivo com acesso a essa tailnet",
o que ainda é mais exposição do que zero autenticação merece.

## Auto-update

Sem `AutoUpdate=` — tag explícita (`v1.7.0`), bump manual (regra 9 do
README raiz). A imagem é Ubuntu mas não tem `curl`/`wget` — o `HealthCmd`
usa uma checagem TCP crua via bash (regra 13, `/dev/tcp` em vez de um
cliente HTTP).

## Backup & Recuperação

```bash
systemctl --user stop lubelogger
tar -czf lubelogger-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes lubelogger
systemctl --user start lubelogger
```

## Comandos úteis

```bash
systemctl --user status lubelogger
podman logs -f lubelogger
```

## Créditos

Deploy Quadlet baseado no [LubeLogger](https://github.com/hargata/lubelog).
Licença original: MIT.
