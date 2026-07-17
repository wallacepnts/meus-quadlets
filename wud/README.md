# WUD (What's Up Docker) — Podman Quadlet (rootless)

Deploy do [What's Up Docker](https://getwud.github.io/wud/) via Podman
Quadlet — observa as imagens de todos os containers do host e avisa
quando existe uma versão mais nova, **sem aplicar nada sozinho**.

## Por que isso, já que existe `podman-auto-update`?

São coisas diferentes. `AutoUpdate=registry` só funciona em tags
**flutuantes** (`:latest`, `:2`) e só sabe comparar o digest da mesma
tag — não existe pra tags fixas. A maioria dos serviços deste repo fica
de propósito em tag fixa + bump manual (ver seção "Serviços neste
repositório" e regra 9 do README raiz) — o WUD cobre exatamente esse
ponto cego: ele detecta que existe uma tag `v2.15.1` mesmo quando o
container está pinado em `v2.9.3`, e só avisa. Decidir se/quando
atualizar continua manual.

## Arquitetura

Container único. Lê o socket do Podman (via `podman.socket`, mesmo
mecanismo já usado pelo [tsdproxy](../tsdproxy/) e pela
[Homepage](../homepage/)) só pra listar containers/imagens — acesso
**somente leitura** (`:ro`). Guarda histórico/config em `/store`
(volume próprio, precisa persistir entre restarts).

## Arquivos

```
quadlet/
└── wud.container   # unit principal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando
- `podman.socket` habilitado (já necessário se
  [tsdproxy](../tsdproxy/)/[homepage](../homepage/) estiverem
  instalados — mesmo socket, reaproveitado)

## Instalação do zero

```bash
# 1. Copiar a unit
mkdir -p ~/.config/containers/systemd
cp quadlet/wud.container ~/.config/containers/systemd/

# 2. Diretório de dados — bind mount exige que já exista antes do start
mkdir -p ~/.config/containers/volumes/wud/store

# 3. Env — schedule da checagem (cron). Padrão do próprio WUD é de hora
#    em hora; diário é suficiente pra maioria dos homelabs e gera bem
#    menos tráfego contra os registries.
mkdir -p ~/.config/containers/env
cat > ~/.config/containers/env/wud.env <<'EOF'
WUD_WATCHER_LOCAL_CRON=0 6 * * *
EOF

# 4. Socket do Podman
systemctl --user enable --now podman.socket

# 5. Subir
systemctl --user daemon-reload
systemctl --user start wud
```

Acessar em `http://localhost:8085` ou, via tailnet,
`https://wud.<seu-tailnet>.ts.net`.

## Autenticação

Sem `WUD_AUTH_BASIC_*` configurado, o próprio WUD loga um aviso
("Anonymous authentication is enabled") e libera acesso sem senha —
mesmo modelo de confiança que a Homepage já usa aqui (sem auth própria,
protegida só por estar na tailnet). Se quiser trocar por autenticação
básica, ver a [documentação de auth do WUD](https://getwud.github.io/wud/#/configuration/authentications/basic).

## Tags não-semver não são observadas

Containers em tag flutuante não-semver (ex.: `:latest`) aparecem no log
como "not a semver and digest watching is disabled" — o WUD não sabe
dizer se há atualização nesse caso a menos que `wud.watch.digest=true`
seja setado como label no container observado (compara digest em vez de
versão). Não é necessário pros serviços deste repo, que ficam quase
todos em tag fixa semver — é só um caso a se ter em mente se algum
serviço novo usar `:latest`.

## Auto-update

Sem `AutoUpdate=` — tag explícita (`8.3.0`), bump manual (regra 9 do
README raiz). Ironia à parte (é a própria ferramenta de observar
atualizações), o padrão deste repositório é o mesmo pra tudo: revisão
manual antes de trocar de versão.

## Comandos úteis

```bash
systemctl --user status wud
podman logs -f wud
```

## Créditos

Deploy Quadlet baseado no [What's Up Docker](https://github.com/getwud/wud),
de [fmartinou](https://github.com/fmartinou). Licença original: MIT.
