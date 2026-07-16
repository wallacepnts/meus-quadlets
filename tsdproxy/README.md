# tsdproxy — Podman Quadlet (rootless)

Deploy do [tsdproxy](https://github.com/almeidapaulopt/tsdproxy) (v2.3.4)
via Podman Quadlet — publica containers na sua tailnet automaticamente, um
nó Tailscale por container, via descoberta por labels. Migrado de um
`docker-compose.yml` (modo Swarm) original. Testado em Podman rootless +
systemd `--user` (openSUSE Tumbleweed, uid 1000), mas os arquivos
`.container`/`.volume` e o conflito de porta são universais pra qualquer
Linux com Podman rootless + systemd — a seção SELinux só se aplica a
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
quadlet/
├── tsdproxy.container    # unit principal
└── tsdproxy-data.volume  # volume gerenciado pelo Podman — estado do tsnet (datadir)

config/
└── tsdproxy.yaml         # config do tsdproxy (bind mount) — precisa existir ANTES do primeiro start
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando
- `podman.socket` habilitado (API compatível com Docker)
- Uma authkey do Tailscale: https://login.tailscale.com/admin/settings/keys

## Instalação do zero

```bash
# 1. Copiar as units
mkdir -p ~/.config/containers/systemd
cp quadlet/tsdproxy.container quadlet/tsdproxy-data.volume ~/.config/containers/systemd/

# 2. Config — o tsdproxy não gera um padrão sozinho, precisa existir antes do start
mkdir -p ~/.config/containers/volumes/tsdproxy/config
cp config/tsdproxy.yaml ~/.config/containers/volumes/tsdproxy/config/

# 3. Secret com a authkey do Tailscale
mkdir -p ~/.config/containers/secrets/tsdproxy
echo -n "SUA_AUTHKEY" > ~/.config/containers/secrets/tsdproxy/authkey.txt
chmod 600 ~/.config/containers/secrets/tsdproxy/authkey.txt
podman secret create authkey ~/.config/containers/secrets/tsdproxy/authkey.txt

# 4. Socket do Podman
systemctl --user enable --now podman.socket

# 5. Subir
systemctl --user daemon-reload
systemctl --user start tsdproxy.service
```

> **Ordem de start:** o Quadlet não sabe nativamente que `tsdproxy.service`
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
[`any-sync-bundle.container`](../any-sync-bundle/quadlet/any-sync-bundle.container).

## Troubleshooting

**Porta 8080 em uso**
Nginx (ou outro serviço) já publicando `8080`. Resolvido usando
`PublishPort=8081:8080` no `tsdproxy.container` — específico desta
máquina, ajustar conforme as portas já ocupadas no seu host
(`ss -tlnp | grep <porta>` pra checar).

**`yaml: unmarshal errors: field dashboard/proxyAccessLog not found`**
A documentação oficial (https://almeidapaulopt.github.io/tsdproxy/docs/getting-started/)
descreve o schema da v3 (beta), mas a imagem usada é `tsdproxy:2` (v2.3.4),
com schema diferente (confirmado lendo o `config.go` da tag `v2.3.4` no
GitHub do projeto). Na v2.3.4, `adminAllowLocalhost` e `proxyAccessLog`
são campos de nível raiz do yaml, não aninhados em `dashboard:`/`log:`
como a doc do site mostra — `config/tsdproxy.yaml` deste repo já segue o
formato certo pra v2.3.4. Ao atualizar pra v3, provavelmente é preciso
voltar ao formato aninhado da doc oficial — checar o `config.go` da tag
correspondente antes de assumir.

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
(`systemctl --user restart tsdproxy.service`). Se não resolver, apagar
`~/.local/share/containers/storage/volumes/tsdproxy-data/_data/default/`
e reiniciar.

## Implantando em outro servidor

**Não copiar** o volume `tsdproxy-data` — guarda o estado/identidade
`tsnet` de cada nó Tailscale criado; copiar faria os nós colidirem entre
si. Cada servidor precisa da própria authkey (gerada na tailnet de
destino) e sobe seus nós do zero.

## Comandos úteis

```bash
systemctl --user status tsdproxy.service
podman logs -f tsdproxy
podman secret ls
semodule -l | grep tsdproxy   # só em SELinux enforcing
```

## Créditos

Deploy Quadlet baseado no [tsdproxy](https://github.com/almeidapaulopt/tsdproxy),
de [Paulo Almeida (@almeidapaulopt)](https://github.com/almeidapaulopt).
Licença original: MIT.
