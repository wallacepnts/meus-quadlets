# any-sync-bundle — Podman Quadlet (rootless)

Deploy do [any-sync-bundle](https://github.com/grishy/any-sync-bundle) (backend
self-hosted do Anytype) via Podman Quadlet, em modo **AIO** (all-in-one —
migrado do `compose.aio.yml` oficial: MongoDB e Redis embutidos na mesma
imagem/container, não mais externos). Testado em Podman rootless + systemd
--user (openSUSE Tumbleweed, uid 1000), mas os arquivos `.container`
são portáveis para qualquer Linux com Podman rootless + systemd.

Fora de escopo aqui (existem no projeto original, não portados): storage S3
(`compose.s3.yml`, MinIO) e reverse proxy via Traefik (`compose.traefik.yml`)
— este setup expõe via Tailscale/tsdproxy em vez de Traefik (ver seção
própria).

## Arquitetura

Um container só. A imagem AIO (**sem** o sufixo `-minimal` da variante
modular) já embute MongoDB 8.0 e Redis Stack — o próprio binário Go do
any-sync-bundle sobe os dois como processos filhos
(`start-all-in-one`, em vez de `start-bundle`), tudo escutando só em
`127.0.0.1` dentro do container. Expõe `33010/tcp` (yamux) e
`33020/udp` (QUIC) pro mundo externo; Mongo/Redis nunca saem do
container.

Um único volume `/data:Z` guarda tudo — a própria imagem organiza os
subdiretórios:

```
/data/
├── bundle-config.yml   # identidade do nó (peerId/peerKey/signingKey)
├── client-config.yml   # regenerado a cada start, não precisa de backup
├── storage/            # dados do bundle (badger)
├── mongo/               # dbpath do MongoDB embutido
└── redis/               # dir do Redis embutido
```

**Diferente do modo modular** (usado originalmente aqui: Postgres → não,
Mongo/Redis em containers separados, rede Podman dedicada,
`Requires=`/`After=` entre units) — trocado a pedido do usuário. Menos
peças móveis (1 container em vez de 3 + 1 rede), mas **ainda exige AVX**
na CPU (o Mongo embutido também é 5.0+) e **não permite pinar a versão
do Mongo separadamente** — ela vem fixa dentro da própria imagem do
any-sync-bundle. Ver seção "Variantes" pra quando isso importa.

## Arquivos

```
quadlet/
└── any-sync-bundle.container   # AIO — servidor + Mongo + Redis embutidos
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando (`systemctl --user status`)
- `loginctl enable-linger <usuário>` — essencial num servidor, senão os
  serviços somem quando a sessão de login encerra
- Checar suporte a AVX na CPU (Mongo 5.0+ exige, embutido): `grep -m1 avx
  /proc/cpuinfo` — sem AVX, este deploy AIO não funciona (não existe
  variante sem AVX pro Mongo embutido; ver seção Variantes)
- Firewall liberando TCP 33010 e UDP 33020 (`firewall-cmd`, `ufw`, `iptables`
  conforme a distro) — sem isso, clientes fora do host não conseguem
  conectar mesmo com o container rodando certo

## Instalação do zero

```bash
# 1. Copiar a unit
mkdir -p ~/.config/containers/systemd/any-sync
cp quadlet/any-sync-bundle.container ~/.config/containers/systemd/any-sync/

# 2. Diretório de dados — bind mount do Podman não cria o diretório do
#    host sozinho (diferente do docker compose); sem isso o container
#    entra em crash-loop com "statfs: no such file or directory"
mkdir -p ~/.config/containers/volumes/any-sync-bundle/data

# 3. Env vars do container — copiar o exemplo e editar
mkdir -p ~/.config/containers/env
cp .env.example ~/.config/containers/env/any-sync-bundle.env
# editar ~/.config/containers/env/any-sync-bundle.env: ANY_SYNC_BUNDLE_INIT_EXTERNAL_ADDRS

# 4. Subir
systemctl --user daemon-reload
systemctl --user start any-sync-bundle
loginctl enable-linger $(whoami)

# 5. Conferir
systemctl --user is-active any-sync-bundle
podman logs any-sync-bundle --tail 20   # procurar "AnySync Bundle is ready!"
```

Depois do primeiro run, o cliente Anytype importa
`~/.config/containers/volumes/any-sync-bundle/data/client-config.yml`.

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
host (`PublishPort=` já presente na unit) — não precisa estar na mesma rede
Podman.

Depois que o node aparecer na tailnet (`tailscale status | grep any-sync`),
adicionar o hostname MagicDNS ao `externalAddr` (ver Solução de problemas) para
que o `client-config.yml` inclua um endereço alcançável de qualquer rede:

```yaml
externalAddr:
    - localhost
    - any-sync.<seu-tailnet>.ts.net
```

## Atualizando a imagem

Tag explícita, igual ao `compose.aio.yml` original — sem `AutoUpdate=`,
bump manual quando quiser:

```ini
Image=ghcr.io/grishy/any-sync-bundle:1.4.3-2026-04-21
```

```bash
# Fazer backup antes (ver seção própria). Editar Image= no .container,
# depois:
systemctl --user daemon-reload
systemctl --user restart any-sync-bundle
```

A tag segue o formato `v[versão-semver]-[data-de-compatibilidade-any-sync]`
(ex.: `1.4.3-2026-04-21` — o sufixo de data é a versão de compatibilidade
do any-sync usada pelos apps do Anytype, não a data do release). Conferir
a versão rodando:

```bash
podman inspect any-sync-bundle --format '{{index .Config.Labels "org.opencontainers.image.version"}}'
```

**A versão do Mongo embutido vem fixa dentro da imagem** — diferente do
modo modular, não dá pra pinar/trocar ela separadamente. Builds recentes
de Mongo 8.0.x (ex. `8.0.26`) se recusam a iniciar em kernel Linux 6.19+
(guard interno do próprio Mongo,
[SERVER-121912](https://jira.mongodb.org/browse/SERVER-121912)) — se uma
troca de tag do any-sync-bundle trouxer uma versão nova do Mongo
embutido que bate nesse bug, a única saída é voltar pro modo modular
(seção Variantes), onde o Mongo é pinável (`mongo:8.0.4`, já testado
funcionando neste kernel).

## Backup & Recuperação

Um volume só (`data/`) — mais simples que o modo modular (que tinha três).
O que importa de verdade é `bundle-config.yml`, que guarda as chaves
privadas do nó (`peerId`/`peerKey`/`signingKey`); perder esse arquivo sem
backup significa que o servidor não pode ser restaurado como o mesmo nó,
só recriado do zero. Já `client-config.yml` é regenerado a cada start e não
precisa de backup.

```bash
# Parar antes do backup (evita capturar o Mongo/Redis embutidos em escrita)
systemctl --user stop any-sync-bundle

tar -czf any-sync-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes any-sync-bundle

systemctl --user start any-sync-bundle
```

**Restaurar:**

```bash
systemctl --user stop any-sync-bundle
podman unshare rm -rf ~/.config/containers/volumes/any-sync-bundle
tar -xzf any-sync-backup-YYYYMMDD-HHMMSS.tar.gz -C ~/.config/containers/volumes
systemctl --user start any-sync-bundle
```

(`podman unshare rm` — não `rm` direto — porque os arquivos do Mongo
embutido são criados com UID remapeado pelo rootless, regra 17 do
README raiz.)

Fazer backup antes de qualquer upgrade manual (trocar a tag do
any-sync-bundle) — a versão do Mongo embutido muda junto, e o incidente
de kernel documentado acima é exatamente o cenário em que isso evitaria
downtime.

**Backup automatizado via [Zerobyte](../zerobyte/):** copiar os arquivos
do Mongo (`.wt`) ou do badger (`storage/`) crus enquanto o processo está
escrevendo é a receita clássica pra um backup corrompido/não restaurável.
O webhook em `backup-webhook/` para o container inteiro antes do Restic
rodar de verdade e religa depois — como é um único container agora, isso
ficou mais simples que no modo modular (não precisa mais coordenar
parada de três serviços). Detalhes e instalação em
[zerobyte/README.md](../zerobyte/README.md#criando-os-jobs-de-backup).

## Implantando em outro servidor / outra tailnet

A unit `.container` é portável e pode ser copiada direto. **Não copiar**
os dados em `volumes/any-sync-bundle/` — cada servidor precisa gerar sua
própria identidade (`peerId`/`peerKey`/`signingKey` em
`bundle-config.yml`, gerados no primeiro run); copiar faria os dois
servidores colidirem como "o mesmo nó".

O que muda por servidor/tailnet:

1. **CPU/AVX** — reconferir (`grep avx /proc/cpuinfo`); sem AVX, só o
   modo modular funciona (seção Variantes).
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

**Modo modular** (Mongo/Redis em containers externos, separados) — não
existe mais neste repositório (removido depois da migração pro AIO,
já testado e funcionando neste host). Use esse modo em vez do AIO se
precisar de:

- **CPU sem AVX** — o modo modular permite trocar o Mongo por uma
  versão 4.4 (sem exigência de AVX); o AIO não tem essa opção, o Mongo
  embutido é sempre 5.0+.
- **Controle manual da versão do Mongo** — pinar numa versão específica
  em vez de aceitar a que vier embutida na imagem do any-sync-bundle
  (relevante se um kernel novo bater no bug SERVER-121912 documentado
  acima e a imagem AIO ainda não tiver corrigido isso upstream).

Se algum desses cenários se aplicar, recriar o modo modular a partir do
[`compose.external.yml`](https://github.com/grishy/any-sync-bundle/blob/main/compose.external.yml)
oficial (Mongo + Redis externos, `start-bundle` em vez de
`start-all-in-one`) — ou resgatar a versão anterior deste README/`.container`
no histórico do git (`git log -- any-sync-bundle/`) como referência de
como este repositório fazia isso antes.

## Solução de problemas

**Containers em crash-loop com `statfs: ... no such file or directory`**
Bind mount do Podman exige que o diretório already exista no host — diferente
do docker compose, que cria sozinho. Rodar o passo 2 da instalação
(`mkdir -p ~/.config/containers/volumes/any-sync-bundle/data`) antes de
subir. Se já entrou em crash-loop e bateu o rate limit do systemd:
`systemctl --user reset-failed any-sync-bundle` depois de criar o diretório.

**Mudei `ANY_SYNC_BUNDLE_INIT_EXTERNAL_ADDRS` e não fez efeito**
Essa env var só é lida na primeira inicialização (quando `bundle-config.yml`
ainda não existe). Depois disso, editar direto
`volumes/any-sync-bundle/data/bundle-config.yml`, campo `externalAddr:`
(lista YAML, aceita múltiplos endereços) e `systemctl --user restart
any-sync-bundle` — isso regenera o `client-config.yml`.

**MongoDB embutido morre com "illegal instruction" (SIGILL/AVX)**
CPU sem AVX — Mongo 5.0+ exige, inclusive embutido no modo AIO. Não tem
variante sem AVX pro AIO — precisa voltar pro modo modular com Mongo
4.4 (seção Variantes).

**Migrando dados do modo modular pro AIO: réplica trava em "Our replica
set config is invalid or we are not a member of it"**
Testado na prática ao migrar este próprio deploy: copiar os arquivos
crus do Mongo (`mongo/db/` → `data/mongo/`) não basta — a configuração
do replica set (`local.system.replset`) fica gravada **dentro** dos
próprios arquivos de dados, referenciando o hostname antigo (`mongo:27017`,
o `NetworkAlias` do modo modular). O Mongo embutido do AIO se identifica
como `127.0.0.1:27017`, então o container fica preso num loop de retry
("failed to initialize mongo replica set, retrying...") até travar de
vez. Conserto: subir um Mongo temporário isolado apontando pro mesmo
diretório de dados, e recorrigir o membro do replica set:

```bash
systemctl --user stop any-sync-bundle

podman run --rm -d --name mongo-repair \
  -v ~/.config/containers/volumes/any-sync-bundle/data/mongo:/data/db:Z \
  -p 27018:27017 \
  docker.io/library/mongo:8.0.4 mongod --replSet rs0 --port 27017 --bind_ip_all

podman exec mongo-repair mongosh --quiet --port 27017 --eval '
var cfg = rs.conf();
cfg.members[0].host = "127.0.0.1:27017";
cfg.version += 1;
rs.reconfig(cfg, {force: true});
'

podman stop mongo-repair
systemctl --user start any-sync-bundle
```

A imagem AIO não tem `mongosh` (só `mongod`, pra manter a imagem menor,
e o repositório apt do Mongo é removido depois da instalação) — por
isso o reparo usa a imagem `mongo:8.0.4` já conhecida deste repo (tem
`mongosh`), num container à parte montando o mesmo `dbpath`, não a
imagem do any-sync-bundle.

**Colisão de nomes com outro deploy Quadlet do any-sync no mesmo host**
O Quadlet nomeia as units pelo *basename* do arquivo — dois arquivos
`any-sync.network` em subdiretórios diferentes colidem silenciosamente
(um sobrescreve o outro no `daemon-reload`, sem erro). Por isso este setup
usa nomes prefixados com `bundle` (`any-sync-bundle.container`) em vez dos
nomes genéricos do exemplo oficial — evita colisão com outros deploys
any-sync (ex.: a stack multi-node oficial).

**Cliente não conecta**
- Conferir se `ANY_SYNC_BUNDLE_INIT_EXTERNAL_ADDRS` (ou o `externalAddr` já
  persistido em `bundle-config.yml`) bate com um endereço realmente
  alcançável a partir do cliente
- Conferir firewall do host: TCP 33010 e UDP 33020 precisam estar abertos
  (`PublishPort=` no Quadlet só expõe a porta pro host — não abre firewall
  sozinho)

## Comandos úteis

```bash
systemctl --user status any-sync-bundle
journalctl --user -u any-sync-bundle -f
podman logs -f any-sync-bundle
```

Não tem `mongosh` dentro do container (ver Solução de problemas) — pra
inspecionar o Mongo embutido diretamente, usar o mesmo truque do
container de reparo (montar `data/mongo` num `mongo:8.0.4` à parte, com
o `any-sync-bundle` **parado** pra evitar dois processos escrevendo no
mesmo `dbpath` ao mesmo tempo).

## Créditos

Deploy Quadlet baseado no [any-sync-bundle](https://github.com/grishy/any-sync-bundle),
de [Sergei G. (@grishy)](https://github.com/grishy). Licença original: MIT.
