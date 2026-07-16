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

Checklist verificado na prática (Podman 5.8.3) — vale como regra padrão
para qualquer serviço novo neste repositório.

### 1. Nome de arquivo único no repo inteiro, não só na pasta

O Quadlet nomeia a unit gerada pelo *basename* do arquivo — **dois
arquivos com o mesmo nome em subpastas diferentes de
`~/.config/containers/systemd/` colidem silenciosamente** (um sobrescreve
o outro no `daemon-reload`, sem aviso). Confirmado na prática: um
`any-sync.network` genérico colidiu com outro deploy no mesmo host.

→ Prefixar todo arquivo com o nome do app, mesmo dentro da própria
subpasta: `any-sync-bundle-net.network`, não `network.network`.

### 2. Secrets são imperativos, não declarativos

**Não existe unit `.secret` no Quadlet.** O gerador só reconhece as
extensões `.container .volume .network .build .pod .kube .artifact
.image` (confirmado em `man podman-systemd.unit`, testado empiricamente:
um arquivo `.secret` é ignorado sem erro, sem log, sem nada). O fluxo
correto:

```bash
# 1. Arquivo-fonte (nunca commitar)
mkdir -p ~/.config/containers/secrets/<app>
echo -n "valor-secreto" > ~/.config/containers/secrets/<app>/senha.txt
chmod 600 ~/.config/containers/secrets/<app>/senha.txt

# 2. Cria o secret no Podman — comando único, uma vez, documentado no
#    README do app como pré-requisito de instalação
podman secret create <app>-senha ~/.config/containers/secrets/<app>/senha.txt
```

```ini
# 3. Referencia no .container
Secret=<app>-senha,target=/run/secrets/senha
```

### 3. `.network`: a chave é `NetworkName=`, não `Name=`

```ini
[Network]
NetworkName=<app>-net
```

`Name=` no grupo `[Network]` dá erro ("unsupported key") — testado.
`Driver=bridge` é o default do Podman, só declarar se quiser deixar
explícito.

### 4. Unit gerada por Quadlet nunca usa `enable`/`disable`

O `[Install]` é aplicado **na hora da geração** — equivale a rodar
`systemctl enable` automaticamente a cada `daemon-reload` (confirmado no
man page: "the generator manually applies the [Install] section... in the
same way systemctl enable does"). `systemctl --user enable app.service` dá
erro ("Unit is transient or generated"). Só usar:

```bash
systemctl --user daemon-reload
systemctl --user start|stop|restart|status <nome>.service
```

### 5. Referenciar `.network`/`.volume` de outro arquivo já injeta a dependência

```ini
Network=meu-app.network
```

já adiciona `Requires=meu-app-network.service` + `After=` automaticamente
no service gerado (confirmado no dry-run) — não precisa declarar isso
manualmente em `[Unit]`.

### 6. Bind mount exige que o diretório do host já exista

Diferente do Docker Compose, o Podman **não cria** o diretório do bind
mount sozinho — sem ele, o container entra em crash-loop com
`statfs: no such file or directory`. Sempre `mkdir -p` os caminhos de
`Volume=` antes do primeiro `start`.

### 7. `$` em `HealthCmd` precisa de escape duplo

Systemd expande `$VAR` em linhas `Exec=` (igual o docker-compose faz com
`$$`). Um `HealthCmd` com subshell (`` $(...) ``) precisa escrever
`$$(...)` no arquivo Quadlet pra sobrar um `$` literal na hora de rodar de
fato.

### 8. `Requires=` propaga parada, não só falha

Reiniciar/parar uma dependência (`systemctl restart mongo.service`)
também para quem a requer (`Requires=mongo.service`) — e se a dependência
falhar nessa janela, quem dependia dela **não volta sozinho**
(`Restart=always` só cobre processo que já rodou e morreu, não job que
falhou por dependência não satisfeita). Depois de corrigir a causa raiz,
subir manualmente.

### 9. Tag flutuante só vale a pena com `HealthCmd` real

`AutoUpdate=registry` + `podman-auto-update.timer` só faz rollback
automático se o container tiver `HealthCmd` configurado — e isso exige
shell/utilitário *dentro da imagem*. Imagens minimal/scratch (sem shell)
não suportam `HealthCmd` nenhum, então auto-update nelas roda sem rede de
segurança nenhuma. Mesmo tags "conservadoras" (major.minor) já quebraram
na prática por motivo alheio ao app (ex.: MongoDB 8.0.26 recusando iniciar
em kernel Linux novo — [SERVER-121912](https://jira.mongodb.org/browse/SERVER-121912)).

**Padrão deste repositório: tag explícita + bump manual por default;
auto-update é opt-in, só pra imagens com `HealthCmd` de verdade e sem
estado crítico de usuário.**

### 10. `PublishPort=` não abre firewall

Só expõe a porta pro host — se o host tiver `firewalld`/`ufw`/`iptables`
ativo, a porta ainda precisa ser liberada separadamente pra acesso
externo.

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
systemctl --user start <app>.service
systemctl --user status <app>.service
journalctl --user -u <app>.service -f
podman exec -it <container> sh   # se a imagem tiver shell
```

Servidor de verdade: `loginctl enable-linger <usuário>` — sem isso, os
serviços somem quando a sessão de login encerra.

## Serviços neste repositório

| Pasta | O quê |
| --- | --- |
| [`any-sync-bundle/`](./any-sync-bundle/) | Backend self-hosted do Anytype ([README](./any-sync-bundle/README.md)) |
