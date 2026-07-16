# Baikal — Podman Quadlet (rootless)

Deploy do [Baikal](https://github.com/sabre-io/Baikal) (servidor
CalDAV/CardDAV self-hosted — calendários e contatos) via Podman Quadlet,
usando a imagem [ckulka/baikal-docker](https://github.com/ckulka/baikal-docker)
(variante nginx + PHP 8.2).

## Arquitetura

Container único, nginx + PHP-FPM, banco SQLite embutido por padrão. Expõe
`80` internamente (mapeado pra `8084` no host — `8080`/`8082`/`8083` já
usados por outros serviços deste repositório).

Dois volumes, como no compose oficial:
- `/var/www/baikal/config` — configuração da aplicação
  (`baikal.yaml`, gerado no primeiro acesso — ver Instalação)
- `/var/www/baikal/Specific` — dados (calendários, contatos, banco)

## Se você já tem outro `baikal` na tailnet

Se já existir outro dispositivo/serviço chamado `baikal` (ex.: um
servidor físico rodando Baikal fora deste repositório), usar
`tsdproxy.name=baikal` aqui colide — mesmo problema documentado no
[tsdproxy](../tsdproxy/) com nós duplicados (`dash`/`dash-1`): mesmo um
dispositivo antigo *offline* ainda reserva o nome, e o novo acaba saindo
como `baikal-1`. Nesse caso, trocar `tsdproxy.name=` (e o `homepage.href`
correspondente) pra algo tipo `baikal-dav` antes de subir.

## Arquivos

```
quadlet/
└── baikal.container   # unit principal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero

```bash
# 1. Copiar a unit
mkdir -p ~/.config/containers/systemd
cp quadlet/baikal.container ~/.config/containers/systemd/

# 2. Diretórios de dados — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/baikal/{config,data}

# 3. Env não-secreto
mkdir -p ~/.config/containers/env
cat > ~/.config/containers/env/baikal.env <<'EOF'
BAIKAL_SERVERNAME=baikal.<seu-tailnet>.ts.net
EOF

# 4. Subir
systemctl --user daemon-reload
systemctl --user start baikal
```

Acessar via [tsdproxy](../tsdproxy/) (tailnet) em
`https://baikal.<seu-tailnet>.ts.net`, ou local em
`http://localhost:8084`.

**Primeiro acesso**: a raiz redireciona pro assistente de instalação
(`/admin/install.php`) — antes de completar esse passo, os logs mostram
`Error reading baikal.yaml file: does not exist`, é esperado (o arquivo
só é criado ao terminar o assistente, onde você define fuso horário e a
senha do admin). Depois de instalado, o painel fica em `/admin/`, e os
endereços CalDAV/CardDAV pros clientes ficam em `/dav.php/calendars/` e
`/dav.php/addressbooks/` (o próprio painel mostra os links exatos por
usuário/calendário depois de criados).

## Auto-update

Sem `AutoUpdate=` — tag explícita (`0.10.1-nginx-php8.2`), bump manual
(regra 9 do README raiz). Imagem Debian com `curl`, healthcheck real.

## Backup & Recuperação

```bash
systemctl --user stop baikal
tar -czf baikal-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes baikal
systemctl --user start baikal
```

## Comandos úteis

```bash
systemctl --user status baikal
podman logs -f baikal
```

## Créditos

Deploy Quadlet usando a imagem [ckulka/baikal-docker](https://github.com/ckulka/baikal-docker)
(MIT), do projeto [Baikal](https://github.com/sabre-io/Baikal)
(GPL-3.0), mantido por [sabre-io](https://github.com/sabre-io).
