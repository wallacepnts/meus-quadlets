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
├── docker.yaml           # define a fonte de descoberta (o socket do Podman)
└── settings.yaml         # statusStyle: dot (bolinha de status em vez de texto)
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

# 2. Config — precisa existir antes do start; se a pasta estiver vazia a
#    própria Homepage gera o resto na primeira vez (bookmarks.yaml etc.)
mkdir -p ~/.config/containers/volumes/homepage/config
cp config/docker.yaml config/settings.yaml ~/.config/containers/volumes/homepage/config/

# 2b. Ícones customizados (opcional) — só precisa existir se for usar,
#     ver seção "Marcando um serviço" abaixo
mkdir -p ~/.config/containers/volumes/homepage/icons

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
systemctl --user start homepage

# 6. Auto-update (ver seção própria abaixo) — timer diário, compartilhado
#    com qualquer outro serviço deste host que também use AutoUpdate=
systemctl --user enable --now podman-auto-update.timer
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

**`href`: `localhost` só funciona vendo o dashboard localmente.** Se a
Homepage também for acessada de outro dispositivo (via tsdproxy/tailnet,
ver acima), `http://localhost:porta` aponta pro próprio dispositivo de
quem está olhando, não pro servidor — o link simplesmente não abre nada.
Se o serviço também estiver exposto na tailnet, usar o endereço dela em
vez de (ou além de) `localhost`:

```ini
Label=homepage.href=https://<nome-do-serviço>.<seu-tailnet>.ts.net
```

Exemplo: `tsdproxy.container` deste repo usa
`homepage.href=http://localhost:8080`, que funciona só localmente. O
próprio tsdproxy já cria um nó `dash` na tailnet pro seu dashboard —
trocar pra `homepage.href=https://dash.<seu-tailnet>.ts.net` deixaria o
link funcionando de qualquer dispositivo.

`icon` aceita `nome.png`/`.svg` (biblioteca [dashboard-icons](https://github.com/homarr-labs/dashboard-icons)),
`mdi-nome` (Material Design Icons), `si-nome` (Simple Icons) ou uma URL
absoluta. Sempre incluir a extensão explicitamente
(`baikal.svg`, não `baikal`) — sem ela, a Homepage tenta especificamente
`.png` (não "detecta o melhor formato"), e se só existir `.svg` o ícone
quebra.

**`si-`/`mdi-` renderizam diferente de `dashboard-icons`.** Prefixados
(`si-`/`mdi-`) viram uma **máscara CSS de cor única** (gradiente por
padrão, ou a cor do tema se `iconStyle: theme` estiver em
`settings.yaml`) — não mostram a imagem original. Ícones "soltos" do
dashboard-icons (`nome.svg`/`.png`) mostram a arte original, com as
cores de verdade. Prefira dashboard-icons quando existir equivalente
(veja se `nome.svg` responde antes de cair pra `si-`/`mdi-`), pra manter
visual consistente entre os cards. Exemplos já em uso neste repo:
[`any-sync-bundle.container`](../any-sync-bundle/quadlet/any-sync-bundle.container)
(`anytype.svg`, sem `href` — não é um serviço HTTP navegável) e
[`tsdproxy.container`](../tsdproxy/quadlet/tsdproxy.container) (`tailscale.svg`).

**Ícone customizado, sem equivalente em dashboard-icons/`si-`/`mdi-`:**
colocar o arquivo em `~/.config/containers/volumes/homepage/icons/` e
referenciar como `Label=homepage.icon=/icons/<arquivo>` (ex.:
`/icons/meu-servico.png`). Precisa reiniciar a própria Homepage depois de
adicionar um ícone novo — limitação do servidor estático do Next.js, não
detecta arquivo novo sozinho (diferente de labels de container, que são
detectadas ao vivo).

Depois de adicionar labels num container existente: `systemctl --user
daemon-reload && systemctl --user restart <nome>` — Homepage
percebe o container atualizado sozinha, não precisa reiniciar a Homepage.

## Auto-update

Ao contrário do any-sync-bundle, a imagem é Alpine com `wget` disponível
— `HealthCmd` real, então `AutoUpdate=registry` tem rollback automático
de verdade (ver regra 9 do README raiz). **Ligado por padrão** neste
repo: `Image=...:latest` + `AutoUpdate=registry` no `.container`,
`podman-auto-update.timer` (diário) cuida do resto — mesmo padrão do
[actual-budget](../actual-budget/). Conferir candidatos antes de confiar
cegamente: `podman auto-update --dry-run`.

## Comandos úteis

```bash
systemctl --user status homepage
podman logs -f homepage
```

## Créditos

Deploy Quadlet baseado no [Homepage](https://github.com/gethomepage/homepage).
Licença original: GPL-3.0.
