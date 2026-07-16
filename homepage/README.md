# homepage — Podman Quadlet (rootless)

Deploy do [Homepage](https://gethomepage.dev) via Podman Quadlet — dashboard
que descobre e exibe outros containers automaticamente, por labels, sem
precisar editar um `services.yaml` manualmente pra cada serviço.

## Arquitetura

Homepage lê o socket do Podman (via `podman.socket`, mesmo mecanismo já
usado pelo [tsdproxy](../tsdproxy/)) só pra listar containers e labels —
acesso **somente leitura** (`:ro`). Qualquer container com
`Label=homepage.group=...` (mínimo necessário) aparece no dashboard
automaticamente; nenhuma entrada manual em `services.yaml` é precisa
quando se usa labels.

## Arquivos

```
quadlet/
└── homepage.container   # unit principal

config/
└── docker.yaml          # define a fonte de descoberta (o socket do Podman)
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando
- `podman.socket` habilitado (já necessário se o [tsdproxy](../tsdproxy/)
  estiver instalado — mesmo socket, reaproveitado)

## Instalação do zero

```bash
# 1. Copiar a unit
mkdir -p ~/.config/containers/systemd
cp quadlet/homepage.container ~/.config/containers/systemd/

# 2. Config — precisa existir antes do start; docker.yaml define a fonte
#    de descoberta, o resto (settings.yaml etc.) a própria Homepage gera
#    na primeira vez se a pasta estiver vazia
mkdir -p ~/.config/containers/volumes/homepage/config
cp config/docker.yaml ~/.config/containers/volumes/homepage/config/

# 3. Env — HOMEPAGE_ALLOWED_HOSTS é obrigatório (allowlist de Host header,
#    formato host:porta; aceita vários separados por vírgula). O
#    .container já vem com labels tsdproxy (nó "homepage" na tailnet),
#    então incluir o hostname MagicDNS aqui também, senão a Homepage
#    rejeita as requisições vindas do tsdproxy com "Host not allowed".
mkdir -p ~/.config/containers/env
cat > ~/.config/containers/env/homepage.env <<'EOF'
HOMEPAGE_ALLOWED_HOSTS=localhost:3000,homepage.<seu-tailnet>.ts.net
EOF

# 4. Socket do Podman
systemctl --user enable --now podman.socket

# 5. Subir
systemctl --user daemon-reload
systemctl --user start homepage.service
```

Acessar em `http://localhost:3000` ou, via tailnet,
`https://homepage.<seu-tailnet>.ts.net` (o `.container` já vem com as
labels do [tsdproxy](../tsdproxy/) — nó próprio criado automaticamente,
igual ao any-sync-bundle).

## Marcando um serviço pra aparecer no dashboard

Em qualquer `.container` (deste repo ou não), adicionar labels
`homepage.*` — puramente opt-in, container sem essas labels simplesmente
não aparece:

```ini
Label=homepage.group=Categoria
Label=homepage.name="Nome exibido"
Label=homepage.icon=si-nome-do-icone
Label=homepage.href=http://endereco:porta
Label=homepage.description="Descrição curta"
```

Valores com espaço precisam de aspas (`Label=chave="valor com espaço"`) —
sem elas o Quadlet corta no primeiro espaço, sem erro nem aviso (regra 12
do README raiz).

`icon` aceita `nome.png`/`.svg` (biblioteca [dashboard-icons](https://github.com/homarr-labs/dashboard-icons)),
`mdi-nome` (Material Design Icons), `si-nome` (Simple Icons) ou uma URL
absoluta. Exemplos já em uso neste repo:
[`any-sync-bundle.container`](../any-sync-bundle/quadlet/any-sync-bundle.container)
(`si-anytype`, sem `href` — não é um serviço HTTP navegável) e
[`tsdproxy.container`](../tsdproxy/quadlet/tsdproxy.container) (`si-tailscale`).

Depois de adicionar labels num container existente: `systemctl --user
daemon-reload && systemctl --user restart <nome>.service` — Homepage
percebe o container atualizado sozinha, não precisa reiniciar a Homepage.

## Auto-update

Ao contrário do any-sync-bundle, a imagem é Alpine com `wget` disponível
— `HealthCmd` real é possível, então `AutoUpdate=registry` teria rollback
automático de verdade (ver regra 9 do README raiz). Não vem ligado por
padrão; pra habilitar, adicionar `AutoUpdate=registry` no `.container` e
trocar a tag pra uma flutuante, depois `systemctl --user enable --now
podman-auto-update.timer`.

## Comandos úteis

```bash
systemctl --user status homepage.service
podman logs -f homepage
```

## Créditos

Deploy Quadlet baseado no [Homepage](https://github.com/gethomepage/homepage).
Licença original: GPL-3.0.
