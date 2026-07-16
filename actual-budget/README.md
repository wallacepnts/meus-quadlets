# Actual Budget — Podman Quadlet (rootless)

Deploy do [Actual Budget](https://actualbudget.org) (servidor de sync)
via Podman Quadlet — orçamento pessoal self-hosted, local-first.

## Arquivos

```
quadlet/
└── actual.container   # unit principal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero

```bash
# 1. Copiar a unit
mkdir -p ~/.config/containers/systemd
cp quadlet/actual.container ~/.config/containers/systemd/

# 2. Diretório de dados — bind mount exige que já exista antes do start.
#    O próprio Actual cria server-files/ e user-files/ dentro dele.
mkdir -p ~/.config/containers/volumes/actual/data

# 3. Env — TZ obrigatório aqui; o resto é opcional (ver
#    https://actualbudget.org/docs/config/)
mkdir -p ~/.config/containers/env
cat > ~/.config/containers/env/actual.env <<'EOF'
TZ=America/Sao_Paulo

# Opcionais — descomentar conforme necessário
# ACTUAL_HTTPS_KEY=/data/selfhost.key
# ACTUAL_HTTPS_CERT=/data/selfhost.crt
# ACTUAL_PORT=5006
# ACTUAL_UPLOAD_FILE_SYNC_SIZE_LIMIT_MB=20
# ACTUAL_UPLOAD_SYNC_ENCRYPTED_FILE_SYNC_SIZE_LIMIT_MB=50
# ACTUAL_UPLOAD_FILE_SIZE_LIMIT_MB=20
EOF

# 4. Subir
systemctl --user daemon-reload
systemctl --user start actual.service
```

Acessar em `http://localhost:5006` ou, via
[tsdproxy](../tsdproxy/) (tailnet), `https://actual.<seu-tailnet>.ts.net`
— trocar isso em `homepage.href` no `.container` e, se for usar o
`HOMEPAGE_ALLOWED_HOSTS`/domínio próprio, ajustar também lá.

## Health check

`HealthCmd` usa o script oficial de health check do próprio projeto
(`node /app/src/scripts/health-check.js`, mesmo comando do
[`docker-compose.yml` oficial](https://github.com/actualbudget/actual/blob/master/packages/sync-server/docker-compose.yml)).
A imagem é Debian, não minimal — tem shell/Node.js disponíveis, então o
health check funciona de verdade (diferente do any-sync-bundle).

## Auto-update

Não vem ligado por padrão (tag explícita `26.1.0`, sem `AutoUpdate=`) —
mesma política do resto do repo (regra 9 do README raiz). Como a imagem
tem `HealthCmd` real, teria rollback automático de verdade se você
decidir habilitar (`AutoUpdate=registry` + tag flutuante + `podman-auto-update.timer`).

Tag pinada mais recente disponível no Docker Hub no momento deste README:
`26.7.0` (rodando `26.1.0`) — checar
`https://hub.docker.com/r/actualbudget/actual-server/tags` antes de trocar.

## Backup & Recuperação

Todo o estado (orçamento, `server-files`, `user-files`) fica em
`volumes/actual/data/`. Parar o serviço antes de copiar:

```bash
systemctl --user stop actual.service
tar -czf actual-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes actual
systemctl --user start actual.service
```

## Comandos úteis

```bash
systemctl --user status actual.service
podman logs -f actual
podman exec actual node /app/src/scripts/health-check.js
```

## Créditos

Deploy Quadlet baseado no [Actual Budget](https://github.com/actualbudget/actual).
Licença original: MIT.
