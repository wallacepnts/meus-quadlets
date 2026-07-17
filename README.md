# meus-quadlets

Coleção pessoal de deploys via [Podman Quadlet](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html)
(rootless), um serviço por pasta. Este README é o padrão de referência —
regras e exemplos verificados na prática, pra seguir em qualquer serviço
novo adicionado aqui.

## Estrutura padrão

```
~/.config/containers/
├── systemd/
│   └── <app>/
│       ├── <app>-net.network
│       └── <app>.container
├── secrets/
│   └── <app>/
│       └── *.txt          # arquivos-fonte dos secrets — nunca versionar
├── env/
│   └── <app>.env
└── volumes/
    └── <app>/
        ├── config/
        └── data/
```

```bash
mkdir -p ~/.config/containers/{systemd,secrets,env,volumes}
```

Cada pasta deste repositório espelha esse layout dentro de `quadlet/`,
pronta pra copiar para `~/.config/containers/systemd/<app>/`.

## Convenções

Regras a seguir em qualquer serviço novo neste repositório (Podman 5.8.3).

### 1. Nome de arquivo único em todo o repositório

O Quadlet nomeia a unit gerada pelo *basename* do arquivo, mesmo entre
subpastas diferentes de `~/.config/containers/systemd/`. Prefixar todo
arquivo com o nome do app: `any-sync-bundle-net.network`.

### 2. Secrets são imperativos

Extensões reconhecidas pelo Quadlet: `.container .volume .network .build
.pod .kube .artifact .image`. Fluxo de secret:

```bash
mkdir -p ~/.config/containers/secrets/<app>
echo -n "valor-secreto" > ~/.config/containers/secrets/<app>/senha.txt
chmod 600 ~/.config/containers/secrets/<app>/senha.txt
podman secret create <app>-senha ~/.config/containers/secrets/<app>/senha.txt
```

```ini
Secret=<app>-senha,target=/run/secrets/senha
```

### 3. `.network`: a chave é `NetworkName=`

```ini
[Network]
NetworkName=<app>-net
```

`Driver=bridge` é o default do Podman, só declarar se quiser deixar
explícito.

### 4. Units geradas por Quadlet: só `start`/`stop`/`restart`/`status`

O `[Install]` já é aplicado na hora da geração.

```bash
systemctl --user daemon-reload
systemctl --user start|stop|restart|status <nome>   # .service é opcional aqui
```

### 5. `Network=`/`Volume=` apontando pra outro arquivo Quadlet já injeta a dependência

```ini
Network=meu-app.network
```

adiciona `Requires=meu-app-network.service` + `After=` automaticamente no
service gerado — não declarar de novo em `[Unit]`.

### 6. Diretórios de bind mount precisam existir antes do primeiro start

`mkdir -p` todo caminho usado em `Volume=` antes de subir o serviço.

### 7. `$` em `HealthCmd` usa escape duplo

```ini
HealthCmd=CMD-SHELL test $$(comando) -eq 1
```

### 8. `Requires=` propaga parada

Parar/reiniciar uma dependência também para quem a requer. Se a
dependência falhar nessa janela, quem dependia dela não volta sozinho —
subir manualmente depois.

### 9. Tag flutuante exige `HealthCmd` real

`AutoUpdate=registry` só tem rollback automático em containers com
`HealthCmd` — que por sua vez exige shell/utilitário dentro da imagem.
Padrão deste repositório: tag explícita + bump manual por default;
auto-update é opt-in, só pra imagens com `HealthCmd` de verdade e sem
estado crítico de usuário.

### 10. `PublishPort=` não abre firewall

Porta liberada no firewall do host (`firewalld`/`ufw`/`iptables`) é passo
separado.

### 11. Créditos ao projeto original

Toda pasta de serviço baseado em outro projeto tem uma seção "Créditos" no
próprio README, linkando o repositório e o autor originais.

### 12. `Label=`/valores com espaço precisam de aspas

```ini
Label=homepage.description="Publica containers na tailnet automaticamente"
```

Sem aspas, o Quadlet corta o valor no primeiro espaço (vira só
`Publica`) — sem erro, sem aviso.

### 13. `HealthCmd` com `localhost`: usar `127.0.0.1`

Em `/etc/hosts` do container, `localhost` resolve pra IPv4 (`127.0.0.1`)
**e** IPv6 (`::1`). Se o processo só escutar em IPv4, um cliente que
prefira IPv6 (`wget`, `curl` sem `-4`) recebe "Connection refused" mesmo
com o serviço no ar — testar com o IP explícito evita o problema.

```ini
HealthCmd=CMD-SHELL wget -q --spider http://127.0.0.1:3000/ || exit 1
```

### 14. `Notify=healthy` exige `HealthCmd` no Quadlet, mesmo com HEALTHCHECK na imagem

Uma imagem já ter `HEALTHCHECK` embutido no Dockerfile não basta —
`Notify=healthy` sem `HealthCmd=` declarado no `.container` falha sempre
com `sdnotify policy "healthy" requires a healthcheck to be set`. Repetir
o mesmo comando da imagem em `HealthCmd=` resolve.

### 15. `Secret=nome,type=env,target=VAR` — segredo como env var, não arquivo

```ini
Secret=minha-app-senha,type=env,target=POSTGRES_PASSWORD
```

Alternativa ao `target=/caminho` (monta arquivo) quando o app espera a
variável de ambiente diretamente, não um arquivo em `/run/secrets/`. Segue
a mesma regra 2 — o secret precisa existir antes via `podman secret
create`.

### 16. Container que precisa ler volumes de outros containers: `SecurityLabelDisable=true`

```ini
SecurityLabelDisable=true
```

Todo volume deste repositório usa `:Z` (rótulo SELinux **privado**,
exclusivo do container dono). Um container terceiro tentando ler esses
caminhos — mesmo só com `:ro` — toma `Permission denied`, porque `:Z` é
exclusivo por design. Ferramentas que precisam enxergar dados de vários
containers ao mesmo tempo (ex.: backup, ver [zerobyte](./zerobyte/))
precisam desligar a confinação SELinux pra esse container específico.
Trade-off consciente, não usar por padrão.

### 17. Mexer manualmente em arquivo criado por container: `podman unshare`, não `sudo`

Rootless Podman mapeia os uids internos do container pra uma faixa de
uids "fantasma" no host (via user namespace, configurado em
`/etc/subuid`/`/etc/subgid`). Um arquivo criado pelo container num bind
mount pertence a esse uid mapeado (ex.: `100100`), não ao seu usuário
(`1000`) — `cp`/`mv`/`rm` direto dá `Permission denied`, porque pro
sistema de arquivos vocês são usuários completamente diferentes.
`sudo` não resolve (troca pra root real, que também não é dono). O
comando certo roda dentro do mesmo namespace que o Podman usa:

```bash
podman unshare mv origem destino
podman unshare rm caminho/arquivo
podman unshare ls -la caminho/
```

Qualquer comando de manipulação de arquivo (`mv`, `cp`, `chown`, `rm`...)
pode ser prefixado com `podman unshare` quando o alvo está dentro de
`volumes/` e pertence ao container, não a você.

**Copiar um arquivo novo *pra dentro*** (não só mover o que já existe)
precisa de um passo a mais — testado na prática: `podman unshare cp`
copia certo (dá acesso de escrita na pasta), mas o arquivo novo fica com
o **seu** uid, diferente dos vizinhos. Ajustar o dono depois, usando
`--reference` pra não precisar adivinhar o número do uid mapeado (varia
por serviço):

```bash
podman unshare cp /origem/arquivo.txt ~/.config/containers/volumes/<app>/<pasta>/
podman unshare chown --reference="$HOME/.config/containers/volumes/<app>/<pasta>/algum-arquivo-existente" \
  ~/.config/containers/volumes/<app>/<pasta>/arquivo.txt
```

### 18. `Label=` não aceita barra invertida no valor

Diferente do `$$` da regra 7 (que é sobre o systemd expandir `$`), aqui
quem recusa é o **parser do próprio Quadlet**: qualquer `\` dentro do
valor de um `Label=` (ex.: uma regex com `\d`, `\.`) faz a linha inteira
ser descartada — `quadlet-generator: unsupported escape char` no
journal, sem erro visível em `systemctl cat` nem em `podman inspect`
(o label simplesmente não existe no container, como se a linha nunca
tivesse sido escrita). Não tem escape que resolva — nem `\\` nem aspas
em volta do valor. Reescrever sem barra invertida: `[0-9]` no lugar de
`\d`, `.` sem escapar (aceitável em regex de filtro, não crítica).
Caso real em [`wud/`](./wud/#wudtagincludewudtagtransform-nada-de--no-valor).

### 19. Uma variável só, pra várias units: `~/.config/environment.d/*.conf`

Quando vários `.container` diferentes precisam apontar pro **mesmo**
path variável (ex.: uma raiz de mídia compartilhada entre vários
serviços — ver [media-stack](./media-stack/)), dá pra evitar editar
cada arquivo com o path hardcoded usando uma variável de ambiente do
systemd, não um `EnvironmentFile=` comum: `EnvironmentFile=` só injeta
env var *dentro do container*, tarde demais pra afetar como o Quadlet
resolve `Volume=`. O mecanismo certo é o `environment.d(5)` do próprio
systemd — `~/.config/environment.d/*.conf` define variáveis pro
ambiente do *manager* `systemd --user` inteiro, e essas variáveis ficam
disponíveis pra expansão `${VAR}` em `Volume=`/`Environment=` de
qualquer unit desse usuário:

```bash
mkdir -p ~/.config/environment.d
cat > ~/.config/environment.d/minha-app.conf <<EOF
MEU_PATH=/caminho/real
EOF
systemctl --user daemon-reload   # obrigatório — sem isso a variável
                                  # nova não existe pro manager ainda
```

```ini
Volume=${MEU_PATH}:/algo:Z
```

Testado na prática: `systemctl cat` mostra `${MEU_PATH}` literal (é só
o texto do arquivo, sem substituição) — o que confunde, parece que não
funcionou — mas `podman inspect` do container já reflete o path
resolvido de verdade, porque a expansão acontece no `ExecStart=` gerado,
na hora que o systemd de fato inicia o processo, não na hora de gerar o
arquivo. Testar com `podman inspect <container> --format
'{{json .Mounts}}'`, não confiar só no `systemctl cat`.

## Anatomia de referência

### `<app>-net.network`

```ini
[Unit]
Description=Rede do <app>

[Network]
NetworkName=<app>-net
```

### `<app>.container`

```ini
[Unit]
Description=<App>
After=<outra-dependencia>.service
Requires=<outra-dependencia>.service

[Container]
Image=<registry>/<imagem>:<tag-explícita>
ContainerName=<app>
Network=<app>-net.network
PublishPort=8080:80

Volume=%h/.config/containers/volumes/<app>/data:/data:Z
EnvironmentFile=%h/.config/containers/env/<app>.env
Secret=<app>-senha,target=/run/secrets/senha

# Só se a imagem tiver shell/utilitários — ver regra 9
HealthCmd=CMD-SHELL <comando>
HealthInterval=5s
HealthTimeout=5s
HealthRetries=12
Notify=healthy

[Service]
Restart=always
TimeoutStartSec=120

[Install]
WantedBy=default.target
```

`:Z` no volume relabela SELinux como privado do container (`:z` minúsculo
= compartilhado entre containers) — só relevante em distros com SELinux
enforcing (Fedora, RHEL, openSUSE Tumbleweed/MicroOS); inofensivo/no-op
nas demais.

`%h` resolve pra `$HOME`; `%t` resolve pra `$XDG_RUNTIME_DIR` (útil pra
sockets como `%t/podman/podman.sock`).

## Ciclo de vida

```bash
systemctl --user daemon-reload
systemctl --user start <app>
systemctl --user status <app>
journalctl --user -u <app> -f
podman exec -it <container> sh   # se a imagem tiver shell
```

Servidor de verdade: `loginctl enable-linger <usuário>` — sem isso, os
serviços somem quando a sessão de login encerra.

### Serviço sozinho (a maioria)

Direto: `systemctl --user restart <app>`.

### Serviço com dependências (ex.: any-sync-bundle, linkwarden)

- **Subir**: só o principal — `systemctl --user start <app>` já sobe as
  dependências primeiro, via `Requires=`.
- **Reiniciar tudo**: idem, `restart` no principal recria a cadeia certa.
- **Reiniciar só uma dependência** (ex.: só o banco, pra aplicar config):
  também **para** quem a requer (regra 8) — se a dependência cair num
  crash-loop nessa janela, quem dependia dela não volta sozinho depois.
  Nesse caso: esperar a dependência ficar `healthy` e só então
  `systemctl --user start <app>` manualmente.
- **Derrubar tudo de propósito**: parar todos de uma vez, não só o
  principal —
  ```bash
  systemctl --user stop <app> <app>-dependencia-1 <app>-dependencia-2
  ```
  (é o padrão usado nos passos de backup de cada README de serviço, por
  este exato motivo — parar só o principal deixa as dependências vivas
  gravando enquanto o backup roda.)

### Conferir depois

```bash
systemctl --user is-active <app>          # rápido, só o status
journalctl --user -u <app> -f              # logs em tempo real
podman ps --filter "name=<app>"            # confirma healthy de verdade
```

### Remover a unit (mantém os dados)

```bash
systemctl --user stop <app> [<dependencias>]
rm ~/.config/containers/systemd/<app>.container   # e .network/.volume se tiver
systemctl --user daemon-reload
systemctl --user reset-failed   # limpa estado de falha residual, se tiver
```

Depois do `daemon-reload` a unit some do `systemctl --user status`. Os
dados continuam em `volumes/<app>/` — dá pra reinstalar depois sem perder
nada.

### Apagar tudo (destrutivo — dados, segredos, config)

```bash
# 1. Confirmar que a unit já foi removida (passo acima)

# 2. Dados — IRREVERSÍVEL sem backup
rm -rf ~/.config/containers/volumes/<app>/

# 3. Env
rm -f ~/.config/containers/env/<app>.env

# 4. Secrets, se o serviço usava (vaultwarden, linkwarden, tsdproxy)
podman secret rm <app>-nome-do-secret
rm -rf ~/.config/containers/secrets/<app>/
```

Duas pegadinhas específicas deste repositório:

- **tsdproxy não desregistra o nó da tailnet sozinho** — apagar o
  container não remove o dispositivo do admin do Tailscale (é assim que
  surgiram os duplicados `dash`/`dash-1` mencionados antes). Pra tirar de
  vez, remover manualmente em
  https://login.tailscale.com/admin/machines.
- **Homepage não precisa de limpeza** — só lê labels de containers vivos
  via socket; some da lista sozinha assim que o container deixa de
  existir.

## Auto-update

Desligado por padrão em todo o repositório (regra 9) — ativar é opt-in,
serviço por serviço, só quando as condições da regra 9 se cumprem
(`HealthCmd` real na imagem + sem dado crítico de terceiros em jogo, ou
disposição consciente de aceitar o risco). [`actual-budget`](./actual-budget/)
é o único exemplo ativo hoje — usar o README dele como referência.

### 1. Ligar o timer (uma vez só, vale pra todo o host)

```bash
systemctl --user enable --now podman-auto-update.timer
```

Ele roda 1x/dia, checando todo container com o label
`io.containers.autoupdate` — não precisa religar por serviço, só essa vez.

### 2. Checar se o serviço é candidato (regra 9)

- Tem `HealthCmd` configurado no `.container`? Sem isso não existe
  rollback automático — o Podman aplica a atualização às cegas.
- Existe uma tag flutuante que faça sentido? Numa tag exata (`1.2.3`) o
  digest nunca muda, `AutoUpdate=` fica sem efeito nenhum. Checar se o
  projeto oferece algo tipo major.minor preso (ex.: `8.0`) antes de virar
  logo pra `:latest` — mas desconfiar mesmo assim (ver o incidente do
  Mongo, regra 9).
- O dado ali é sensível/crítico o bastante pra preferir revisão manual
  antes de cada bump? (cofre de senhas, backend com estado real —
  provavelmente não vale a pena.)

### 3. Ativar no `.container`

```ini
Image=<registro>/<imagem>:<tag-flutuante>
AutoUpdate=registry
```

```bash
systemctl --user daemon-reload
systemctl --user restart <app>
```

### 4. Conferir e, se precisar, reverter

```bash
podman auto-update --dry-run              # prévia, sem aplicar nada
podman auto-update --rollback <container> # reverter manualmente
```

Fazer backup antes de qualquer bump de versão relevante — o rollback
automático só cobre "não ficou `healthy`", não cobre "ficou healthy mas
com um bug silencioso nos dados" (ver seção Backup de cada serviço).

## Migrando de outro servidor

Trazer um backup de um servidor diferente (não uma instalação nova do
zero — pra isso, ver "Implantando em outro servidor" de cada serviço) pra
este host.

### 1. No servidor antigo

Parar o serviço e gerar o backup como já documentado na seção Backup de
cada README — `tar` de `volumes/<app>/` — incluindo também
`~/.config/containers/secrets/<app>/` se o serviço usar secrets
(linkwarden, vaultwarden, tsdproxy): sem eles os dados restaurados não
autenticam/decodificam.

### 2. Transferir

Os dois hosts já estão na mesma tailnet — `scp`/`rsync` direto entre eles
pela tailnet é o caminho mais simples: já é criptografado, sem storage
intermediário, sem configuração extra.

### 3. Neste servidor

Instalar o Quadlet normalmente, mas **sem dar o primeiro `start`** —
extrair o backup em `volumes/<app>/` antes disso, recriar os secrets a
partir dos arquivos copiados (`podman secret create` com o mesmo
conteúdo), só então `systemctl --user start`.

### O que checar antes de considerar migrado

- **Identidade criptográfica**: any-sync-bundle e tsdproxy geram
  identidade própria no primeiro run (`peerId`/`peerKey`; estado
  `tsnet`). Trazer esses dados faz o servidor novo *ser* a continuação do
  antigo (mesmo nó, clientes existentes reconhecem). Não trazer gera uma
  instância nova e independente — o oposto do que "Implantando em outro
  servidor" de cada serviço recomenda pra instalação do zero.
- **Endereços gravados nos dados**: `externalAddr` (any-sync-bundle),
  `DOMAIN` (vaultwarden), `NEXTAUTH_URL`/cookies (linkwarden) referenciam
  o hostname do servidor antigo — ajustar pro endereço da tailnet deste
  host depois de restaurar.
- **Compatibilidade de versão**: se o servidor antigo estava numa versão
  bem atrás da tag pinada aqui, checar o changelog antes — principalmente
  linkwarden (migrations do Postgres) e vaultwarden (schema do SQLite).
- **Não apagar o servidor antigo até confirmar** que o novo está saudável
  e acessível — se algo der errado na migração, ainda dá pra voltar.

## Serviços neste repositório

|  | Apps | Descrição | AutoUpdate |
| --- | --- | --- | --- |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/actual-budget.svg" width="28" height="28" alt=""> | [Actual Budget](./actual-budget) | Orçamento pessoal self-hosted ([README](./actual-budget/README.md)) | ✅ |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/anytype.svg" width="28" height="28" alt=""> | [any-sync-bundle](./any-sync-bundle) | Backend self-hosted do Anytype ([README](./any-sync-bundle/README.md)) | ❌ |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/baikal.svg" width="28" height="28" alt=""> | [Baikal](./baikal) | Servidor CalDAV/CardDAV self-hosted ([README](./baikal/README.md)) | ❌ |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/gitea.svg" width="28" height="28" alt=""> | [Gitea](./gitea) | Servidor Git self-hosted ([README](./gitea/README.md)) | ❌ |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/home-assistant.svg" width="28" height="28" alt=""> | [Home Assistant](./home-assistant) | Automação residencial self-hosted ([README](./home-assistant/README.md)) | ❌ |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/png/homepage.png" width="28" height="28" alt=""> | [homepage](./homepage) | Dashboard que descobre containers por labels ([README](./homepage/README.md)) | ✅ |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/jellyfin.svg" width="28" height="28" alt=""> | [Jellyfin](./jellyfin) | Servidor de mídia self-hosted ([README](./jellyfin/README.md)) | ❌ |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/png/linkwarden.png" width="28" height="28" alt=""> | [Linkwarden](./linkwarden) | Gerenciador de links/bookmarks self-hosted ([README](./linkwarden/README.md)) | ❌ |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/png/lubelogger.png" width="28" height="28" alt=""> | [LubeLogger](./lubelogger) | Controle de manutenção veicular self-hosted ([README](./lubelogger/README.md)) | ❌ |
|  | [Media Stack](./media-stack) | Prowlarr, Sonarr, Radarr, Lidarr, Bazarr, Seerr, Gluetun, Deluge, SABnzbd, Jellyfin — automação de mídia, mesma raiz de dados compartilhada ([README](./media-stack/README.md)) | ❌ |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/tailscale.svg" width="28" height="28" alt=""> | [tsdproxy](./tsdproxy) | Publica containers na tailnet automaticamente, por labels ([README](./tsdproxy/README.md)) | ❌ |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/vaultwarden.svg" width="28" height="28" alt=""> | [Vaultwarden](./vaultwarden) | Cofre de senhas self-hosted, compatível com Bitwarden ([README](./vaultwarden/README.md)) | ❌ |
| <img src="https://cdn.jsdelivr.net/gh/getwud/wud@main/ui/public/img/icons/android-chrome-512x512.png" width="28" height="28" alt=""> | [WUD (What's Up Docker)](./wud) | Monitora atualizações de imagem sem aplicar sozinho ([README](./wud/README.md)) | ❌ |
| <img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/png/zerobyte.png" width="28" height="28" alt=""> | [Zerobyte](./zerobyte) | Automação de backup (Restic) pros outros serviços ([README](./zerobyte/README.md)) | ❌ |

### O que o AutoUpdate precisa pra funcionar direito

Três peças, as três obrigatórias:

1. **Tag flutuante** (`:latest`, `:2`, etc.) — `AutoUpdate=registry` compara
   o digest da tag contra o registry; numa tag pinada (`:v1.4.5`) o digest
   nunca muda, então nunca há nada pra atualizar.
2. **`AutoUpdate=registry`** no `.container` — sem essa linha o Podman
   nunca verifica, mesmo com tag flutuante.
3. **`podman-auto-update.timer` ativo** (`systemctl --user enable --now
   podman-auto-update.timer`) — é ele quem dispara a checagem
   periodicamente (diária, por padrão do systemd). Um timer só,
   compartilhado por todos os containers com `AutoUpdate=` deste usuário.

**A parte que faz isso ser seguro, não só automático: `HealthCmd` real.**
Rollback automático (voltar pra imagem anterior se a atualização quebrar)
só existe se o container tiver um healthcheck de verdade — o que por sua
vez exige shell/cliente HTTP dentro da imagem (`wget`/`curl`, ou uma
checagem TCP crua tipo a do lubelogger). Sem isso, `AutoUpdate=registry`
ainda troca a imagem e reinicia sozinho, só que **sem rede de segurança**:
se a build nova estiver quebrada, fica quebrada até alguém notar e
arrumar manualmente. Ver regra 9, no início deste README.

Checar candidatos antes de confiar cegamente: `podman auto-update
--dry-run`.

### Por que a maioria está desligado

Padrão deste repositório: tag explícita + bump manual por default,
auto-update é opt-in. Motivos específicos, documentados no README de
cada serviço (seção "Auto-update" ou "Atualizando as imagens"):

- **any-sync-bundle** — a imagem principal é minimal, sem shell (sem
  `HealthCmd` real possível); o Mongo além disso tem uma regressão
  upstream conhecida (kernel 6.19+) que pede revisão manual antes de
  trocar de tag, healthcheck ou não.
- **linkwarden** — a versão do Meilisearch é a que o `docker-compose.yml`
  oficial recomenda; trocar sem checar compatibilidade pode quebrar a
  busca. Migrations do Postgres também pedem revisão antes de subir de
  versão (um healthcheck "ok" não significa "a migration rodou certo").
- **vaultwarden** — a imagem tem `wget`/`curl` (daria pra habilitar com
  rollback de verdade), mas é um cofre de senhas: revisão manual antes de
  atualizar é o padrão aqui de propósito, não uma limitação técnica.
- **zerobyte** — mesmo raciocínio do vaultwarden: guarda a senha de
  acesso a todos os outros backups, prefiro revisão manual mesmo tendo
  `HealthCmd` real.
- **lubelogger** — imagem Ubuntu sem `curl`/`wget`; o `HealthCmd` usa uma
  checagem TCP crua (regra 13), então nem entra na conversa de
  auto-update com rollback de verdade sem trocar a estratégia de
  healthcheck primeiro.
- **baikal** — mesmo raciocínio do vaultwarden: banco SQLite embutido
  (calendários/contatos), healthcheck não cobre migração de schema.
- **tsdproxy** — sem motivo técnico específico, só não foi avaliado/ligado
  ainda (já usa uma tag de major flutuante, `:2`, mas sem `AutoUpdate=`
  isso não dispara sozinho).
