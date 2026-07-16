# Zerobyte — Podman Quadlet (rootless)

Deploy do [Zerobyte](https://github.com/nicotsx/zerobyte) (automação de
backup baseada em [Restic](https://restic.net)) via Podman Quadlet —
agenda, monitora e gerencia backups encriptados de todos os outros
serviços deste repositório, com interface web.

## Arquitetura

Container único. Monta como **fonte** (somente leitura) tudo que este
repositório gerencia — `~/.config/containers/volumes/` e
`~/.config/containers/secrets/` — e dois **destinos**: um diretório local
neste host e um repositório remoto via rclone (qualquer um dos 40+
provedores suportados).

### Por que `SecurityLabelDisable=true`

Cada serviço deste repo já usa `:Z` (rótulo SELinux **privado**, exclusivo
daquele container) nos próprios volumes. Um container terceiro — o
zerobyte — tentando ler através de vários diretórios com rótulos privados
diferentes toma `Permission denied`, mesmo montando só como `:ro`. A
saída é desligar a confinação SELinux só pro zerobyte
(`--security-opt label=disable`). Trade-off consciente: ele só monta
essas fontes como somente-leitura, mas fica sem a barreira extra do
SELinux — aceitável aqui porque é exatamente o papel de uma ferramenta de
backup (precisa enxergar tudo), e o container não é exposto fora da
tailnet.

### rclone é só destino, não fonte

O Zerobyte usa rclone de dois jeitos possíveis: como **repositório**
(onde os backups encriptados ficam guardados) ou como **volume de
origem** (montar armazenamento na nuvem como se fosse um disco local, via
FUSE). Só o primeiro modo é usado aqui — por isso **não** precisamos de
`SYS_ADMIN`/`--device /dev/fuse` (exigidos só pro segundo modo).

## Arquivos

```
quadlet/
└── zerobyte.container         # unit principal

../linkwarden/pgdump/
├── linkwarden-pgdump.service  # dump do Postgres do linkwarden (systemd comum, não Quadlet)
└── linkwarden-pgdump.timer    # roda diariamente antes do job do Zerobyte
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando
- `rclone` instalado no **host** (só pra rodar o assistente de config
  interativo uma vez — o binário não entra no container)

## Instalação do zero

```bash
# 1. Copiar a unit
mkdir -p ~/.config/containers/systemd
cp quadlet/zerobyte.container ~/.config/containers/systemd/

# 2. Diretórios — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/zerobyte/data
mkdir -p ~/backups/zerobyte-local
mkdir -p ~/.config/rclone

# 3. Configurar o destino rclone — interativo, roda no HOST (não no
#    container). Escolher o provedor (S3, Google Drive, Backblaze B2 etc.)
#    quando o assistente perguntar.
rclone config

# 4. APP_SECRET — chave de 32+ bytes usada pelo Zerobyte pra encriptar o
#    que ele guarda no próprio banco (não é a senha do repositório Restic
#    — essa é definida na hora de criar cada repositório, pela interface)
mkdir -p ~/.config/containers/secrets/zerobyte
openssl rand -hex 32 | tr -d '\n' > ~/.config/containers/secrets/zerobyte/app-secret.txt
chmod 600 ~/.config/containers/secrets/zerobyte/app-secret.txt
podman secret create zerobyte-app-secret ~/.config/containers/secrets/zerobyte/app-secret.txt

# 5. Env não-secreto
mkdir -p ~/.config/containers/env
cat > ~/.config/containers/env/zerobyte.env <<'EOF'
BASE_URL=https://zerobyte.<seu-tailnet>.ts.net
TZ=America/Sao_Paulo
PORT=4096
RESTIC_HOSTNAME=<nome-deste-host>
EOF

# 6. Subir
systemctl --user daemon-reload
systemctl --user start zerobyte
```

Acessar via [tsdproxy](../tsdproxy/) (tailnet) em
`https://zerobyte.<seu-tailnet>.ts.net`, ou local em
`http://localhost:4096`.

## Configurando os dois destinos (repositórios) pela interface

Depois do primeiro acesso, criar dois repositórios na UI:

- **Local**: caminho `/repositories/local` (é onde
  `~/backups/zerobyte-local` está montado dentro do container)
- **rclone**: escolher o remote configurado no passo 3 da instalação

Cada repositório pede uma senha de encriptação Restic própria — **essa
senha não fica em nenhum arquivo deste repositório, guardar em local
seguro** (ex.: no próprio [vaultwarden](../vaultwarden/) deste repo,
ironia à parte). Sem ela, os snapshots existem mas não dá pra restaurar
nada.

## Criando os jobs de backup

Fontes disponíveis dentro do container: `/sources/volumes` (espelha
`~/.config/containers/volumes/`) e `/sources/secrets` (espelha
`~/.config/containers/secrets/`). Um job por serviço, ou um job só
cobrindo tudo — a granularidade é sua.

**Atenção especial ao `linkwarden`**: o Zerobyte não tem hook de
pré-backup (não roda comando nenhum antes de arquivar) — ele só copia o
que encontrar no caminho configurado. Copiar os arquivos crus do Postgres
(`/sources/volumes/linkwarden/postgres`) **enquanto o banco está
rodando** é um jeito clássico de gerar um backup corrompido/não
restaurável. Por isso:

- **Excluir** `linkwarden/postgres` do job de backup do linkwarden
  (Zerobyte/Restic suportam padrão de exclusão na configuração do job)
- Incluir no lugar `linkwarden/pg-dump/linkwarden.dump` — gerado pelo
  timer `linkwarden-pgdump.timer` (ver abaixo), que roda `pg_dump`
  (dump lógico, seguro pra copiar mesmo com o banco ativo) todo dia às
  **2h50**
- Agendar o job do linkwarden no Zerobyte pra depois disso (ex.: 3h) —
  os dois horários não são sincronizados automaticamente, é
  responsabilidade sua manter essa ordem

```bash
# Instalar o timer de dump (fora do Quadlet — é systemd comum)
cp ../linkwarden/pgdump/linkwarden-pgdump.service ../linkwarden/pgdump/linkwarden-pgdump.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now linkwarden-pgdump.timer

# Testar manualmente
systemctl --user start linkwarden-pgdump
ls -la ~/.config/containers/volumes/linkwarden/pg-dump/
```

O any-sync-bundle (Mongo/Redis) tem o mesmo tipo de risco em menor grau —
não montei uma solução pra ele ainda; se for backupear esse serviço
também, vale o mesmo raciocínio (`mongodump`/`redis BGSAVE` antes,
excluir os data dirs crus).

## Auto-update

Sem `AutoUpdate=` — tag explícita (`v0.41.0`), bump manual (regra 9 do
README raiz). Imagem Alpine com `wget`, `HealthCmd` real configurado —
daria pra habilitar auto-update de verdade se quiser, mas pra uma
ferramenta que segura a senha de acesso a todos os seus backups, prefiro
revisão manual.

## Comandos úteis

```bash
systemctl --user status zerobyte
podman logs -f zerobyte
podman exec zerobyte sh -c "ls /sources/volumes"   # conferir o que está visível
```

## Créditos

Deploy Quadlet baseado no [Zerobyte](https://github.com/nicotsx/zerobyte),
de [nicotsx](https://github.com/nicotsx). Licença original: AGPL-3.0.
