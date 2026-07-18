# Radicale — Podman Quadlet (rootless)

Deploy do [Radicale](https://radicale.org) (servidor CalDAV/CardDAV leve e
minimalista — calendários e contatos) via Podman Quadlet, usando a
imagem [tomsquest/docker-radicale](https://github.com/tomsquest/docker-radicale)
(bem mais hardened que a média: filesystem raiz somente leitura,
capabilities reduzidas ao mínimo, sem privilégio novo).

Mesmo propósito do [Baikal](../baikal/) já neste repositório — instalado
à parte, não como substituto (nada aqui apaga o Baikal).

## Arquitetura

Container único. Filesystem raiz **somente leitura** — só `/data`
(dados: calendários, contatos) é gravável; `/config` é montado como
`:ro` de propósito (o config em si não deveria mudar em runtime).
Capabilities: `DropCapability=all` + só `chown`/`setuid`/`setgid`
(entrypoint ajusta o dono de `/data` no primeiro start) e `kill`
(supervisor interno) — tudo isso replicado do compose oficial, que já é
propositalmente restritivo.

Autenticação via **htpasswd** (`/config/config` + `/config/users`) —
sem isso, o Radicale roda **sem autenticação nenhuma** por padrão
(`auth type = none`), então configurar isso desde o primeiro start é
importante, diferente do Baikal (que já força criar conta no assistente
de instalação).

**`config/config` precisa ser o arquivo completo**, não só a seção
`[auth]` — montar em `/config/config` **substitui** o config padrão da
imagem inteiro, não faz merge. A imagem só funciona porque o default
embutido tem `filesystem_folder = /data/collections` (dentro do único
volume gravável); um `config/config` customizado sem essa linha faz o
Radicale cair no default de software (`/var/lib/radicale/collections`),
que está no filesystem raiz somente leitura — testado na prática, trava
com `[Errno 30] Read-only file system` no start. `config/config` deste
repositório já é o arquivo completo, com só a seção `[auth]` trocada de
`type = none` pra `htpasswd`.

## Arquivos

```
radicale.container   # unit principal

config/
└── config            # arquivo de config completo (não só auth) — vem deste repo

birthday-calendar/
└── create_birthday_calendar.py   # script vendorizado, ver Créditos

birthday-sync/
├── radicale-birthday-sync.service # roda o script acima via "podman exec"
└── radicale-birthday-sync.timer   # dispara o service periodicamente
```

`config/users` (hash de senha) **não** vem do repositório — gerado no
passo 3 da instalação, nunca versionado (regra 2 do README raiz).

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando
- `python3` com o módulo `bcrypt` (`pip3 install --user bcrypt`) — só
  pra gerar o hash da senha no passo de instalação

## Instalação do zero

```bash
# 1. Baixar a unit (sem precisar clonar o repositório)
mkdir -p ~/.config/containers/systemd
wget -P ~/.config/containers/systemd/ \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/radicale/radicale.container

# 2. Diretórios de dados — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/radicale/{data,config}
wget -O ~/.config/containers/volumes/radicale/config/config \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/radicale/config/config

# 3. Usuário/senha — hash bcrypt gerado localmente, formato htpasswd
#    (usuario:hash, um por linha). O arquivo /config/users precisa ser
#    legível por qualquer uid (mundo-legível) porque o container roda
#    com um uid interno fixo (2999) que não é o seu — sem UserNS=keep-id
#    nesta imagem (ver Arquitetura), é a única forma dele enxergar o
#    arquivo.
read -p "Usuário do Radicale: " RADICALE_USER
read -s -p "Senha do Radicale: " RADICALE_PW; echo
RADICALE_USER="$RADICALE_USER" RADICALE_PW="$RADICALE_PW" python3 -c "
import bcrypt, os
user = os.environ['RADICALE_USER']
pw = os.environ['RADICALE_PW'].encode()
h = bcrypt.hashpw(pw, bcrypt.gensalt()).decode()
print(f'{user}:{h}')
" > ~/.config/containers/volumes/radicale/config/users
unset RADICALE_PW
chmod 644 ~/.config/containers/volumes/radicale/config/users

# 4. Env não-secreto — baixar o exemplo
mkdir -p ~/.config/containers/env
wget -O ~/.config/containers/env/radicale.env \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/radicale/.env.example

# 5. Subir
systemctl --user daemon-reload
systemctl --user start radicale
```

Acessar via [tsdproxy](../tsdproxy/) (tailnet) em
`https://radicale.<seu-tailnet>.ts.net`, ou local em
`http://localhost:5232` — pede o usuário/senha criados no passo 3.
Endereços CalDAV/CardDAV pros clientes:
`https://radicale.<seu-tailnet>.ts.net/<usuario>/<nome-da-coleção>/`
(a própria UI web, acessível na raiz, cria calendários/agendas e mostra
o link exato de cada um).

## Adicionar mais usuários depois

Repetir o passo 3 em modo append (`>>` em vez de `>`), uma linha por
usuário — o `htpasswd_filename` aceita várias linhas, uma conta por
linha.

## Calendário de aniversários automático

Baseado em [iBigQ/radicale-birthday-calendar](https://github.com/iBigQ/radicale-birthday-calendar)
(MIT) — script que lê os contatos com aniversário (`BDAY`) de todos os
addressbooks de um usuário e mantém um calendário `birthdays` sempre
atualizado, recorrente todo ano.

**Não é via hook** — o projeto original é pensado pro mecanismo de hook
do Radicale (`[storage] hook = <comando>`, disparado a cada escrita),
mas essa versão do Radicale (3.7.6) **removeu** esse mecanismo genérico:
o sistema de hook agora é plugin-based, com só três tipos internos
(`none`/`rabbitmq`/`email`), sem opção de "rodar um comando qualquer"
— testado na prática, confirmado lendo o código-fonte da própria imagem
(`radicale/hook/__init__.py`). Em vez disso, este repositório usa um
**timer periódico** (a cada 30 min, `radicale-birthday-sync.timer`) que
varre todos os contatos via `podman exec` e regenera o calendário —
mais simples e não depende da API interna (não-documentada) de hooks do
Radicale, ao custo de não ser instantâneo.

```bash
# 1. Baixar o script e os pacotes Python que ele precisa (uma vez só —
#    não dá pra instalar no site-packages padrão, filesystem raiz é
#    somente leitura, então instala em /data, referenciado via
#    PYTHONPATH já presente no .container)
mkdir -p ~/.config/containers/volumes/radicale/data/birthday-calendar
wget -O ~/.config/containers/volumes/radicale/data/birthday-calendar/create_birthday_calendar.py \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/radicale/birthday-calendar/create_birthday_calendar.py
podman run --rm \
  -v ~/.config/containers/volumes/radicale/data:/data:Z \
  --entrypoint pip3 \
  docker.io/tomsquest/docker-radicale:3.7.6.0 \
  install --target=/data/python-libs --no-cache-dir vobject python-dateutil

# 2. Baixar e ativar o timer (systemd comum, fora do Quadlet)
wget -P ~/.config/systemd/user/ \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/radicale/birthday-sync/radicale-birthday-sync.service \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/radicale/birthday-sync/radicale-birthday-sync.timer
systemctl --user daemon-reload
systemctl --user enable --now radicale-birthday-sync.timer

# Testar manualmente (não precisa esperar os 30 min)
systemctl --user start radicale-birthday-sync.service
```

Cada usuário que tiver um contato com `BDAY` preenchido ganha um
calendário `birthdays` automaticamente na primeira execução — visível
junto dos outros na raiz da conta, sincronizável como qualquer outro
calendário CalDAV.

**Variáveis opcionais** (`radicale.env`, ver `.env.example`):
`BIRTHDAY_CALENDAR_COLOR` (cor do calendário; sem isso, escolhe uma cor
aleatória na primeira execução) e `BIRTHDAY_REMINDER_AT_HOUR` (lembrete
N horas antes da meia-noite do dia do aniversário).

## Solução de problemas

**`error setting cgroup config ... memory.swap.max: no such file or
directory`** — o compose oficial limita a `256M` de RAM
(`--memory=256m`), mas isso depende do controller `memory` estar
delegado ao cgroup do usuário (`systemd`/`logind`), o que não é garantido
em rootless — testado na prática: neste host só `pids` está delegado
(conferir com `cat /sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/cgroup.controllers`).
Por isso o `.container` deste repositório **não** define `--memory`,
só `--pids-limit` (que já funciona). Se seu host tiver `memory`
delegado, adicionar `PodmanArgs=--memory=256m` de volta é seguro.

## Auto-update

Sem `AutoUpdate=` — tag explícita (`3.7.6.0`), bump manual (regra 9 do
README raiz). A imagem tem `curl`/healthcheck real (daria pra habilitar
com rollback de verdade), mas calendários/contatos são dado real do
usuário — revisão manual antes de atualizar, mesmo raciocínio do baikal.

## Backup & Recuperação

```bash
systemctl --user stop radicale
tar -czf radicale-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes radicale
systemctl --user start radicale
```

`config/users` já está incluído (fica dentro de `volumes/radicale/`,
junto com `data/`).

## Comandos úteis

```bash
systemctl --user status radicale
podman logs -f radicale
podman exec radicale curl -fs http://127.0.0.1:5232
```

## Créditos

Deploy Quadlet usando a imagem
[tomsquest/docker-radicale](https://github.com/tomsquest/docker-radicale)
(MIT), do projeto [Radicale](https://github.com/Kozea/Radicale)
(GPL-3.0). Calendário de aniversários baseado em
[iBigQ/radicale-birthday-calendar](https://github.com/iBigQ/radicale-birthday-calendar)
(MIT).
