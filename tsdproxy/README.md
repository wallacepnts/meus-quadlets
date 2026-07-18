# tsdproxy — Podman Quadlet (rootless)

Deploy do [tsdproxy](https://github.com/almeidapaulopt/tsdproxy) (v2.3.4)
via Podman Quadlet — publica containers na sua tailnet automaticamente, um
nó Tailscale por container, via descoberta por labels. Migrado de um
`docker-compose.yml` (modo Swarm) original. Testado em Podman rootless +
systemd `--user` (openSUSE Tumbleweed, uid 1000), mas o arquivo
`.container` e o conflito de porta são universais pra qualquer Linux com
Podman rootless + systemd — a seção SELinux só se aplica a
distros com SELinux enforcing por padrão (Fedora, RHEL/CentOS, openSUSE
Tumbleweed/MicroOS); em AppArmor (Ubuntu/Debian) ou sem MAC esse passo
específico não é necessário.

## Arquitetura

O tsdproxy fala a API do Docker, não a do Podman — mas o socket do Podman
é compatível, então basta expor `podman.sock` como `docker.sock` dentro do
container (não precisa instalar Docker). Ele observa esse socket, e pra
cada container com `Label=tsdproxy.enable=true` cria um nó Tailscale
próprio (`tsdproxy.name=<nome>`) e faz proxy do tráfego da tailnet pro
container — TCP/UDP puro, não só HTTP (ver uso real em
[`any-sync-bundle`](../any-sync-bundle/)).

## Arquivos

```
tsdproxy.container      # unit principal

config/
└── tsdproxy.yaml         # config do tsdproxy (bind mount) — precisa existir ANTES do primeiro start
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando
- `podman.socket` habilitado (API compatível com Docker)
- Uma authkey do Tailscale: https://login.tailscale.com/admin/settings/keys

## Instalação do zero

```bash
# 1. Baixar a unit (sem precisar clonar o repositório)
mkdir -p ~/.config/containers/systemd
wget -P ~/.config/containers/systemd/ \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/tsdproxy/tsdproxy.container

# 2. Diretórios de dados — bind mount exige que já existam antes do start.
#    O tsdproxy não gera um config padrão sozinho, então config/tsdproxy.yaml
#    também precisa vir de algum lugar antes do primeiro start.
mkdir -p ~/.config/containers/volumes/tsdproxy/{data,config}
wget -O ~/.config/containers/volumes/tsdproxy/config/tsdproxy.yaml \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/tsdproxy/config/tsdproxy.yaml

# 3. Secret com a authkey do Tailscale
mkdir -p ~/.config/containers/secrets/tsdproxy
echo -n "SUA_AUTHKEY" > ~/.config/containers/secrets/tsdproxy/authkey.txt
chmod 600 ~/.config/containers/secrets/tsdproxy/authkey.txt
podman secret create authkey ~/.config/containers/secrets/tsdproxy/authkey.txt

# 4. Socket do Podman
systemctl --user enable --now podman.socket

# 5. Subir
systemctl --user daemon-reload
systemctl --user start tsdproxy
```

> **Ordem de start:** o Quadlet não sabe nativamente que `tsdproxy`
> depende do `podman.socket` — sem declarar isso, num reboot nada garante
> que o socket já exista quando `default.target` sobe o container (corrida
> silenciosa, não determinística). Por isso o `[Unit]` do
> `tsdproxy.container` tem `Requires=podman.socket` + `After=podman.socket`.

No `tsdproxy.container`, o `%t` do Quadlet resolve pra `$XDG_RUNTIME_DIR`
— `Volume=%t/podman/podman.sock:/var/run/docker.sock:z` nesta máquina
(uid 1000) equivale a montar `/run/user/1000/podman/podman.sock`.

## Publicando um container na tailnet

Em qualquer `.container` (deste repo ou não), adicionar labels e garantir
que a porta esteja publicada no host (`PublishPort=`) — o tsdproxy resolve
o alvo por ela, não precisa estar na mesma rede Podman:

```ini
Label=tsdproxy.enable=true
Label=tsdproxy.name=meu-app
Label=tsdproxy.port.web=443/https:8080/http
```

Exemplo real de proxy TCP/UDP puro (não-HTTP) em
[`any-sync-bundle.container`](../any-sync-bundle/any-sync-bundle.container).

## Solução de problemas

**`yaml: unmarshal errors: field dashboard/proxyAccessLog not found`**
A documentação oficial (https://almeidapaulopt.github.io/tsdproxy/docs/getting-started/)
mostra `adminAllowLocalhost` aninhado em `dashboard:` e `proxyAccessLog`
aninhado em `log:`. Não é uma diferença de schema entre v2 e v3: conferindo
o `config.go` de `v2.3.4` e também da `v3.0.0-beta.3` (a v3 mais recente
publicada) no GitHub do projeto, os dois campos estão na **raiz** do yaml
nas duas versões — a doc do site está desatualizada/errada em relação ao
código real, em ambas. `config/tsdproxy.yaml` deste repo usa o formato de
raiz (o que realmente funciona). Ao trocar de versão, testar contra o
`config.go` da tag correspondente antes de confiar na doc do site.

**`permission denied while trying to connect to the docker API`**
Só relevante em sistemas com SELinux enforcing. Causa: SELinux, pra
sockets Unix, valida o contexto do *processo que criou o socket* (aqui,
o `podman system service`, rotulado `container_runtime_t`), não o label
do arquivo em si — relabelar o bind mount com `:z`/`:Z` não resolve.

Diagnóstico (nesta ordem, se precisar refazer em outra máquina):
```bash
getenforce                                    # ou: cat /sys/fs/selinux/enforce
sudo ausearch -m avc -ts recent               # procurar AVC "connectto"
# se não aparecer nada (política silencia via "dontaudit"):
sudo semodule -DB                             # desabilita dontaudit temporariamente
# reproduzir o erro (reiniciar o container)
sudo ausearch -m avc -ts recent -c tsdproxyd  # deve aparecer o AVC connectto
sudo semodule -B                              # restaura dontaudit
```

AVC relevante:
```
avc: denied { connectto } comm="tsdproxyd" path="/run/user/1000/podman/podman.sock"
scontext=...:container_t tcontext=...:container_runtime_t tclass=unix_stream_socket
```

`container_connect_any` (boolean do SELinux) não resolve esse caso
específico no policy do openSUSE. Correção: módulo customizado.
```bash
sudo ausearch -m avc -ts recent -c tsdproxyd | audit2allow -M tsdproxy_dockersock
sudo semodule -i tsdproxy_dockersock.pp
```
Conferir com `semodule -l | grep tsdproxy`. Remover com
`sudo semodule -r tsdproxy_dockersock`.

**`NeedsLogin` sem auth URL após subir**
Estado do `tsnet` corrompido por vários restarts durante um crash-loop
anterior (containers subindo e morrendo repetidamente antes do socket
funcionar). O próprio log avisa: "Restart tsdproxy to auto-recover, or
manually delete the proxy data directory." Costuma resolver sozinho no
restart seguinte, já com o socket acessível
(`systemctl --user restart tsdproxy`). Se não resolver, apagar
`~/.config/containers/volumes/tsdproxy/data/default/` e reiniciar.

## Nós somem sozinhos da tailnet (auth key ephemeral)

Por padrão, apagar um container **não** remove o nó dele do admin console
do Tailscale (ver "Duas pegadinhas específicas" no
[README raiz](../README.md#apagar-tudo-destrutivo--dados-segredos-config))
— fica órfão até alguém remover manualmente. Dá pra automatizar isso
gerando a authkey como **ephemeral**: um nó registrado com uma chave
ephemeral some sozinho da tailnet uns 30–60 min depois de ficar offline,
sem intervenção manual.

**Onde isso é decidido**: só na authkey em si, gerada com a opção
**Ephemeral** marcada em
https://login.tailscale.com/admin/settings/keys — não é uma label nem
config do tsdproxy. Testado por um usuário e confirmado pelo mantenedor:
a label `tsdproxy.ephemeral=true` **não** ativa isso
([discussão #71](https://github.com/almeidapaulopt/tsdproxy/discussions/71)).

```bash
# 1. Gerar a authkey nova em https://login.tailscale.com/admin/settings/keys
#    com "Reusable" E "Ephemeral" marcados (Reusable já era obrigatório —
#    uma chave só registra todos os serviços proxiados por este tsdproxy)

# 2. Trocar o secret
podman secret rm authkey
echo -n "NOVA_AUTHKEY" > ~/.config/containers/secrets/tsdproxy/authkey.txt
podman secret create authkey ~/.config/containers/secrets/tsdproxy/authkey.txt

# 3. Reiniciar tsdproxy (e any-sync-bundle, que gera nó próprio direto,
#    sem passar pelo tsdproxy)
systemctl --user restart tsdproxy any-sync-bundle
```

**Duas ressalvas importantes**:
- Só vale pra nós **registrados depois da troca** — a chave usada no
  registro decide a ephemeralidade daquele nó, não é retroativo. Os nós
  já existentes continuam exatamente como estão até serem re-registrados
  (logout + novo login com a chave nova).
- Não limpa os órfãos duplicados que já existem hoje (`dash`/`dash-1` e
  parecidos) — esses precisam de remoção manual uma vez, como já
  documentado.

## Implantando em outro servidor

**Não copiar** `volumes/tsdproxy/data/` — guarda o estado/identidade
`tsnet` de cada nó Tailscale criado; copiar faria os nós colidirem entre
si. Cada servidor precisa da própria authkey (gerada na tailnet de
destino) e sobe seus nós do zero.

## Comandos úteis

```bash
systemctl --user status tsdproxy
podman logs -f tsdproxy
podman secret ls
semodule -l | grep tsdproxy   # só em SELinux enforcing
```

## Créditos

Deploy Quadlet baseado no [tsdproxy](https://github.com/almeidapaulopt/tsdproxy),
de [Paulo Almeida (@almeidapaulopt)](https://github.com/almeidapaulopt).
Licença original: MIT.
