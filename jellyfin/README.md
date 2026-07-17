# Jellyfin — Podman Quadlet (rootless)

Deploy do [Jellyfin](https://jellyfin.org) (servidor de mídia self-hosted)
via Podman Quadlet, baseado no [guia oficial pra Podman](https://jellyfin.org/docs/general/installation/container/?method=podman).

## Decisões deste deploy

- **Path da mídia não vem definido** — de propósito. Diferente dos
  outros volumes deste repositório (que ficam todos sob
  `~/.config/containers/volumes/<app>/`), a biblioteca de mídia é
  gerenciada por fora, varia de host pra host, e pode ser grande demais
  pra fazer sentido dentro dessa estrutura. Quem for instalar escolhe o
  path real na hora (ver Instalação).
- **Transcodificação por hardware documentada por fabricante, não
  configurada por padrão** — Intel/AMD (`/dev/dri`, simples) e NVIDIA
  (NVIDIA Container Toolkit + CDI, mais trabalhoso) têm caminhos bem
  diferentes; ver seção própria abaixo e habilitar o que bater com o
  hardware de quem for instalar.
- **Rede bridge normal** (`PublishPort=8096:8096`), não `host` — mesma
  lógica já aplicada ao [Home Assistant](../home-assistant/): perde
  autodiscovery de clientes na LAN (porta `7359/udp`, broadcast — não
  atravessa bridge/NAT direito), mas mantém o isolamento de rede padrão
  deste repositório. Sem autodiscovery, os clientes Jellyfin (apps de
  TV, mobile etc.) pedem o endereço do servidor manualmente na primeira
  configuração — funciona normal, só não aparece sozinho na lista.

## Arquitetura

Container único, imagem oficial (Debian + jellyfin-ffmpeg já com suporte
a NVENC/QSV/VAAPI compilado, independente de hardware disponível). Dois
volumes fixos (`config`, `cache`) mais o volume de mídia (variável, ver
acima).

`UserNS=keep-id` — mapeia o container pro mesmo uid do usuário que roda
o Podman (recomendação oficial do próprio Jellyfin pra Podman), pra ler
a pasta de mídia sem precisar chown nem lidar com o remapeamento uid
rootless padrão que o resto deste repositório usa.

## Arquivos

```
quadlet/
└── jellyfin.container   # unit principal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero

```bash
# 1. Copiar a unit
mkdir -p ~/.config/containers/systemd
cp quadlet/jellyfin.container ~/.config/containers/systemd/

# 2. Diretórios de dados — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/jellyfin/{config,cache}

# 3. Mídia — editar o .container recém-copiado e descomentar/ajustar:
#      Volume=/path/to/sua/midia:/media:ro,Z
#    trocando pro path real da sua biblioteca. Pode ter mais de uma
#    linha Volume= se a mídia estiver espalhada em pastas diferentes
#    (ex.: filmes e séries em discos separados).

# 4. Subir
systemctl --user daemon-reload
systemctl --user start jellyfin
```

Acessar via [tsdproxy](../tsdproxy/) (tailnet) em
`https://jellyfin.<seu-tailnet>.ts.net`, ou local em
`http://localhost:8096` — a raiz redireciona pro assistente de
instalação na primeira vez (idioma, conta admin, adicionar biblioteca
apontando pro path montado em `/media`).

## Transcodificação por hardware

Sem isso, transcodificação usa só CPU — funciona, mas não escala bem
pra vários streams simultâneos ou 4K. Adicionar no `.container` **antes**
de subir (ou editar e `systemctl --user daemon-reload && systemctl
--user restart jellyfin` depois):

### Intel/AMD (`/dev/dri`, VAAPI/QSV)

```ini
AddDevice=/dev/dri:/dev/dri
```

Em host com SELinux enforcing, também pode ser necessário:

```bash
sudo setsebool -P container_use_dri_devices 1
```

Depois, em Painel administrativo → Reprodução, selecionar VAAPI (AMD)
ou QSV (Intel) como aceleração de hardware.

### NVIDIA (NVENC/NVDEC) — mais trabalhoso

Precisa do [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
instalado no host primeiro (driver NVIDIA já funcionando é pré-requisito
implícito). Depois, gerar a especificação CDI — em rootless, no
namespace do próprio usuário:

```bash
mkdir -p ~/.config/cdi
nvidia-ctk cdi generate --output=$HOME/.config/cdi/nvidia.yaml
```

Em host com SELinux enforcing:

```bash
sudo setsebool -P container_use_devices 1
```

Adicionar no `.container`:

```ini
AddDevice=nvidia.com/gpu=all
```

Depois, em Painel administrativo → Reprodução, selecionar NVIDIA NVENC.
A partir do NVIDIA Container Toolkit v1.18.0 existe um serviço
`nvidia-cdi-refresh` que mantém a especificação CDI atualizada sozinha
(driver atualizado, GPU trocada etc.) — sem ele, refazer o
`nvidia-ctk cdi generate` manualmente após qualquer mudança de driver.

## Auto-update

Sem `AutoUpdate=` — tag explícita (`10.11.11`), bump manual (regra 9 do
README raiz). Imagem tem `curl`, `HealthCmd` real configurado — mas
biblioteca/metadados/histórico de reprodução ficam num banco SQLite
embutido em `/config`, mesma cautela do [baikal](../baikal/)/[gitea](../gitea/):
healthcheck confere só se o servidor HTTP responde, não se uma migração
de schema numa troca de versão rodou certo.

## Backup & Recuperação

```bash
systemctl --user stop jellyfin
tar -czf jellyfin-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes jellyfin
systemctl --user start jellyfin
```

Só `config`/`cache` — a mídia em si não faz parte deste backup (fica
fora de `~/.config/containers/volumes/`, gerenciada separadamente por
quem instalou).

## Comandos úteis

```bash
systemctl --user status jellyfin
podman logs -f jellyfin
```

## Créditos

Deploy Quadlet baseado no [Jellyfin](https://github.com/jellyfin/jellyfin).
Licença original: GPL-2.0.
