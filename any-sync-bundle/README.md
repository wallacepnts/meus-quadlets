# any-sync-bundle — Podman Quadlet (rootless)

Deploy do [any-sync-bundle](https://github.com/grishy/any-sync-bundle) (backend
self-hosted do Anytype) via Podman Quadlet, migrado do `compose.external.yml`
oficial (MongoDB + Redis externos). Testado em Podman rootless + systemd
--user (openSUSE Tumbleweed, uid 1000), mas os arquivos `.container`/`.network`
são portáveis para qualquer Linux com Podman rootless + systemd.

Fora de escopo aqui (existem no projeto original, não portados): storage S3
(`compose.s3.yml`, MinIO) e reverse proxy via Traefik (`compose.traefik.yml`)
— este setup expõe via Tailscale/tsdproxy em vez de Traefik (ver seção
própria).

## Arquitetura

Três containers na rede `any-sync-bundle-net.network`:

- `any-sync-bundle-mongo` — MongoDB 8.0.4 (replica set de nó único, necessário
  mesmo standalone)
- `any-sync-bundle-redis` — Redis Stack (com módulo `redisbloom`)
- `any-sync-bundle` — o binário do any-sync-bundle, expõe `33010/tcp`
  (yamux) e `33020/udp` (QUIC)

`any-sync-bundle` só sobe depois que mongo e redis reportam `healthy`
(`Notify=healthy` + `Requires=`/`After=` no `[Unit]`, equivalente ao
`depends_on: condition: service_healthy` do compose).

## Arquivos

```
quadlet/
├── any-sync-bundle-net.network      # rede dedicada
├── any-sync-mongo.container         # MongoDB 8.0.4 (CPUs com AVX)
├── any-sync-mongo-legacy.container  # MongoDB 4.4 (CPUs sem AVX — ver Troubleshooting)
├── any-sync-bundle-redis.container  # Redis Stack 7.4.0-v7
└── any-sync-bundle.container        # servidor any-sync-bundle 1.4.3-2026-04-21-minimal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando (`systemctl --user status`)
- `loginctl enable-linger <usuário>` — essencial num servidor, senão os
  serviços somem quando a sessão de login encerra
- Checar suporte a AVX na CPU (Mongo 5.0+ exige): `grep -m1 avx /proc/cpuinfo`
  — se não tiver, usar a variante `any-sync-mongo-legacy.container` (veja
  Troubleshooting)
- Firewall liberando TCP 33010 e UDP 33020 (`firewall-cmd`, `ufw`, `iptables`
  conforme a distro) — sem isso, clientes fora do host não conseguem
  conectar mesmo com o container rodando certo

## Instalação do zero

```bash
# 1. Copiar as units para uma subpasta dedicada (renomear a legacy só se a
#    CPU não tiver AVX). Quadlet escaneia subdiretórios de
#    ~/.config/containers/systemd/ normalmente — usar uma subpasta por app
#    facilita organização quando o host roda vários serviços.
mkdir -p ~/.config/containers/systemd/any-sync
cp quadlet/any-sync-bundle-net.network \
   quadlet/any-sync-bundle-redis.container \
   quadlet/any-sync-bundle.container \
   quadlet/any-sync-mongo.container \
   ~/.config/containers/systemd/any-sync/
# CPU sem AVX: usar a legacy no lugar da normal
#   cp quadlet/any-sync-mongo-legacy.container ~/.config/containers/systemd/any-sync/any-sync-mongo.container

# 2. Criar os diretórios de dados ANTES de subir — bind mount do Podman não
#    cria o diretório do host sozinho (diferente do docker compose); sem isso
#    os containers entram em crash-loop com "statfs: no such file or directory"
mkdir -p ~/.config/containers/volumes/any-sync-bundle/{mongo,redis,bundle}

# 3. Env vars do container principal
mkdir -p ~/.config/containers/env
cat > ~/.config/containers/env/any-sync-bundle.env <<'EOF'
# Advertise address(es) clients devem usar (separado por vírgula). Só é lido
# na primeira inicialização — depois disso, editar externalAddr em
# volumes/any-sync-bundle/bundle/bundle-config.yml (ver Troubleshooting).
ANY_SYNC_BUNDLE_INIT_EXTERNAL_ADDRS=SEU_IP_OU_HOSTNAME
ANY_SYNC_BUNDLE_INIT_MONGO_URI=mongodb://mongo:27017/?replicaSet=rs0
ANY_SYNC_BUNDLE_INIT_REDIS_URI=redis://redis:6379/

# Limite de storage por espaço, em bytes (default: 1 TiB)
# 1 GiB=1073741824  10 GiB=10737418240  150 GiB=161061273600  1 TiB=1099511627776  2 TiB=2199023255552
# ANY_SYNC_BUNDLE_INIT_FILENODE_DEFAULT_LIMIT=1099511627776
EOF

# 4. Subir
systemctl --user daemon-reload
systemctl --user start any-sync-bundle.service   # sobe mongo e redis primeiro via Requires=
loginctl enable-linger $(whoami)

# 5. Conferir
systemctl --user is-active any-sync-mongo any-sync-bundle-redis any-sync-bundle
podman logs any-sync-bundle --tail 20   # procurar "AnySync Bundle is ready!"
```

Depois do primeiro run, o cliente Anytype importa
`~/.config/containers/volumes/any-sync-bundle/bundle/client-config.yml`.

> Unit `.container` do Quadlet gera o service com o **mesmo nome do arquivo**
> (`any-sync-mongo.container` → `any-sync-mongo.service`), sem sufixo extra —
> diferente de `.network`/`.volume`, que ganham `-network`/`-volume` no nome
> do service gerado. `enable`/`disable` não funcionam em units geradas por
> Quadlet ("Unit is transient or generated") — o `[Install]` já é processado
> na hora da geração; use só `start`/`stop`/`restart`.

## Exposição via Tailscale (tsdproxy) — opcional

Se o servidor já roda [tsdproxy](https://github.com/almeidapaulopt/tsdproxy)
para publicar containers na tailnet, o any-sync-bundle pode ser exposto do
mesmo jeito. tsdproxy v2.3.4 suporta proxy **TCP/UDP puro** (não só HTTP),
via labels no `[Container]`:

```ini
Label=tsdproxy.enable=true
Label=tsdproxy.name=any-sync
Label=tsdproxy.port.sync=33010/tcp:33010/tcp
Label=tsdproxy.port.quic=33020/udp:33020/udp
```

(já incluído em `any-sync-bundle.container` neste repo). O tsdproxy descobre
o container via socket do Podman e resolve o alvo pela porta publicada no
host (`PublishPort=` já presente nas units) — não precisa estar na mesma rede
Podman.

Depois que o node aparecer na tailnet (`tailscale status | grep any-sync`),
adicionar o hostname MagicDNS ao `externalAddr` (ver Troubleshooting) para
que o `client-config.yml` inclua um endereço alcançável de qualquer rede:

```yaml
externalAddr:
    - localhost
    - any-sync.<seu-tailnet>.ts.net
```

## Atualizando as imagens

As três imagens ficam em tags explícitas, iguais às do `compose.external.yml`
original — sem `AutoUpdate=`, bump manual quando quiser:

| Container | Tag atual |
| --- | --- |
| `any-sync-bundle` | `1.4.3-2026-04-21-minimal` |
| `any-sync-bundle-mongo` | `8.0.4` |
| `any-sync-bundle-redis` | `7.4.0-v7` |

```bash
# Fazer backup antes (ver seção própria). Editar Image= no .container
# correspondente pra nova tag, depois:
systemctl --user daemon-reload
systemctl --user restart <nome>.service
```

A tag do any-sync-bundle segue o formato
`v[versão-semver]-[data-de-compatibilidade-any-sync]` (ex.:
`1.4.3-2026-04-21` — o sufixo de data é a versão de compatibilidade do
any-sync usada pelos apps do Anytype, não a data do release). Conferir a
versão rodando (a imagem `-minimal` não tem `--version` executável via
`podman exec`, sem shell):

```bash
podman inspect any-sync-bundle --format '{{index .Config.Labels "org.opencontainers.image.version"}}'
```

Ao trocar a tag do Mongo: builds recentes de Mongo 8.0.x (ex. `8.0.26`) se
recusam a iniciar em kernel Linux 6.19+ (guard interno do próprio Mongo,
[SERVER-121912](https://jira.mongodb.org/browse/SERVER-121912)) — conferir
`uname -r` antes de sair de `8.0.4`.

## Backup & Recuperação

Diferente do `./data/` único do projeto original, aqui os dados ficam
separados em três volumes. Para um backup completo, os três precisam ser
incluídos — principalmente `bundle-config.yml`, que guarda as chaves
privadas do nó (`peerId`/`peerKey`/`signingKey`); perder esse arquivo sem
backup significa que o servidor não pode ser restaurado como o mesmo nó,
só recriado do zero. Já `client-config.yml` é regenerado a cada start e não
precisa de backup.

```bash
# Parar tudo antes do backup (evita capturar o Mongo/Redis em escrita)
systemctl --user stop any-sync-bundle any-sync-mongo any-sync-bundle-redis

tar -czf any-sync-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes any-sync-bundle

systemctl --user start any-sync-bundle   # sobe mongo e redis via Requires=
```

**Restaurar:**

```bash
systemctl --user stop any-sync-bundle any-sync-mongo any-sync-bundle-redis
rm -rf ~/.config/containers/volumes/any-sync-bundle
tar -xzf any-sync-backup-YYYYMMDD-HHMMSS.tar.gz -C ~/.config/containers/volumes
systemctl --user start any-sync-bundle
```

Fazer backup antes de qualquer upgrade manual (Mongo, Redis, ou trocar a
tag do bundle manualmente) — é a mesma recomendação do projeto original, e
o incidente do Mongo documentado acima é exatamente o cenário em que isso
teria evitado downtime.

## Implantando em outro servidor / outra tailnet

Os arquivos `.container`/`.network` são portáveis e podem ser copiados
direto. **Não copiar** os dados em `volumes/any-sync-bundle/` — cada servidor
precisa gerar sua própria identidade (`peerId`/`peerKey`/`signingKey` em
`bundle-config.yml`, gerados no primeiro run); copiar faria os dois
servidores colidirem como "o mesmo nó".

O que muda por servidor/tailnet:

1. **CPU/AVX** — reconferir (`grep avx /proc/cpuinfo`) e trocar para
   `any-sync-mongo-legacy.container` se necessário.
2. **`ANY_SYNC_BUNDLE_INIT_EXTERNAL_ADDRS`** — IP/hostname alcançável desse
   servidor específico.
3. **tsdproxy (se usar)** — authkey **da nova tailnet**
   (https://login.tailscale.com/admin/settings/keys daquela conta), novo
   secret Podman (`podman secret create authkey ...`); `Label=tsdproxy.name=`
   pode continuar `any-sync` sem conflito, já que é outra tailnet. O sufixo
   MagicDNS também muda (`tailscale status --json` no servidor novo).
4. **Portas já em uso** — checar `ss -tlnp | grep -E '33010|33020'` antes de
   subir, se o host já tiver outro serviço nessas portas.

## Variantes

- `any-sync-mongo-legacy.container` — Mongo 4.4, para CPUs sem AVX (mais
  comuns em VPS antigas/baratas). Ver comentário no topo do arquivo: usa o
  mesmo `ContainerName`/`NetworkAlias` do `any-sync-mongo.container` normal,
  então só um dos dois pode estar em `~/.config/containers/systemd/` por vez
  — copiar a legacy renomeada para `any-sync-mongo.container`.

## Troubleshooting

**Containers em crash-loop com `statfs: ... no such file or directory`**
Bind mount do Podman exige que o diretório already exista no host — diferente
do docker compose, que cria sozinho. Rodar o passo 2 da instalação
(`mkdir -p ~/.config/containers/volumes/any-sync-bundle/{mongo,redis,bundle}`)
antes de subir. Se já entrou em crash-loop e bateu o rate limit do systemd:
`systemctl --user reset-failed <service>` depois de criar os diretórios.

**Mudei `ANY_SYNC_BUNDLE_INIT_EXTERNAL_ADDRS` e não fez efeito**
Essa env var só é lida na primeira inicialização (quando `bundle-config.yml`
ainda não existe). Depois disso, editar direto
`volumes/any-sync-bundle/bundle/externalAddr:` (lista YAML, aceita múltiplos
endereços) e `systemctl --user restart any-sync-bundle.service` — isso
regenera o `client-config.yml`.

**MongoDB morre com "illegal instruction" (SIGILL/AIO)**
CPU sem AVX — Mongo 5.0+ exige. Usar `any-sync-mongo-legacy.container`
(Mongo 4.4) no lugar do normal.

**Healthcheck do Mongo com `$$` no `HealthCmd`**
Necessário — o systemd também expande `$` em linhas `Exec=` (igual ao
docker-compose), então `$$` vira um único `$` literal só na hora de executar
o healthcheck de fato. Não simplificar para `$`.

**Colisão de nomes com outro deploy Quadlet do any-sync no mesmo host**
O Quadlet nomeia as units pelo *basename* do arquivo — dois arquivos
`any-sync.network` em subdiretórios diferentes colidem silenciosamente
(um sobrescreve o outro no `daemon-reload`, sem erro). Por isso este setup
usa nomes prefixados com `bundle` (`any-sync-bundle-net.network`,
`any-sync-bundle-redis.container`) em vez dos nomes genéricos do exemplo
oficial — evita colisão com outros deploys any-sync (ex.: a stack multi-node
oficial, que usa `any-sync.network`/`any-sync-redis.container`).

**MongoDB se recusa a iniciar: "Linux kernel versions 6.19 and newer has a known incompatibility"**
Regressão do próprio Mongo (não é bug deste setup) — builds recentes do
Mongo 8.0.x têm um guard que bloqueia start em kernel 6.19+
([SERVER-121912](https://jira.mongodb.org/browse/SERVER-121912)). Checar
`uname -r`; se for 6.19+, usar `mongo:8.0.4` fixo (já é o padrão deste
repo) em vez de qualquer tag `8.0`/`8`/`latest`. Não incluir Mongo no
auto-update enquanto esse issue não for resolvido upstream.

**Reiniciei mongo/redis e o `any-sync-bundle` ficou parado ("Dependency failed")**
`Requires=` propaga parada: reiniciar `any-sync-mongo.service` ou
`any-sync-bundle-redis.service` diretamente também para o
`any-sync-bundle.service` (que os requer), e se um dos dois falhar nessa
janela (ex.: crash-loop batendo `start-limit-hit`), o bundle não sobe de
volta sozinho — `Restart=always` só cobre processo que já rodou e morreu,
não job que falhou por dependência não satisfeita. Depois de corrigir a
causa raiz, subir manualmente: `systemctl --user start any-sync-bundle.service`.

**Cliente não conecta**
- Conferir se `ANY_SYNC_BUNDLE_INIT_EXTERNAL_ADDRS` (ou o `externalAddr` já
  persistido em `bundle-config.yml`) bate com um endereço realmente
  alcançável a partir do cliente
- Conferir firewall do host: TCP 33010 e UDP 33020 precisam estar abertos
  (`PublishPort=` no Quadlet só expõe a porta pro host — não abre firewall
  sozinho)

## Comandos úteis

```bash
systemctl --user status any-sync-mongo any-sync-bundle-redis any-sync-bundle
journalctl --user -u any-sync-bundle -f
podman logs -f any-sync-bundle
podman exec any-sync-bundle-mongo mongosh --eval 'rs.status()'
```

## Créditos

Deploy Quadlet baseado no [any-sync-bundle](https://github.com/grishy/any-sync-bundle),
de [Sergei G. (@grishy)](https://github.com/grishy). Licença original: MIT.
