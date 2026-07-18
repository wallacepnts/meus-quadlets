# Ollama — Podman Quadlet (rootless)

Deploy do [Ollama](https://ollama.com) (servidor de LLMs locais — baixa,
roda e serve modelos via API HTTP compatível) via Podman Quadlet,
seguindo o [guia oficial de Docker](https://docs.ollama.com/docker).

## Arquitetura

Container único. **CPU-only por padrão** — sem GPU, roda em qualquer
host, mais lento pra modelos grandes. Ver seções abaixo pra ativar
aceleração por GPU (NVIDIA ou AMD), sem trocar de imagem no caso da
NVIDIA (mesma imagem detecta e usa a GPU se ela for exposta ao
container) ou trocando pra tag `:rocm` no caso da AMD.

Um volume só (`/root/.ollama`) — guarda os modelos baixados (podem ficar
grandes, vários GB cada) e configuração interna.

Healthcheck usa o próprio binário `ollama` (`ollama list`, fala com o
servidor local via `OLLAMA_HOST` padrão) — a imagem não tem
`curl`/`wget` pra um healthcheck HTTP tradicional.

## Arquivos

```
ollama-net.network   # rede bridge isolada
ollama.container      # unit principal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero (CPU-only)

```bash
# 1. Baixar as units (sem precisar clonar o repositório)
mkdir -p ~/.config/containers/systemd
wget -P ~/.config/containers/systemd/ \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/ollama/ollama-net.network \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/ollama/ollama.container

# 2. Diretório de dados — bind mount exige que já exista antes do start
mkdir -p ~/.config/containers/volumes/ollama/data

# 3. Subir
systemctl --user daemon-reload
systemctl --user start ollama
```

Baixar e rodar um modelo:

```bash
podman exec -it ollama ollama run llama3.2
```

API HTTP em `http://<ip-do-host>:11434`, ou via [tsdproxy](../tsdproxy/)
(tailnet) em `https://ollama.<seu-tailnet>.ts.net`.

## Ativar GPU NVIDIA

Requer o **NVIDIA Container Toolkit** configurado pro Podman (gera uma
spec CDI — Container Device Interface — que o Podman rootless usa pra
expor a GPU sem precisar rodar como root). Não vem pronto por padrão
neste repositório porque é uma mudança de pacotes do host, fora do
escopo de um `.container` sozinho.

```bash
# 1. Instalar o toolkit (openSUSE — adicionar o repo oficial da NVIDIA
#    primeiro, se ainda não tiver; nomes variam por distro, ver
#    https://github.com/NVIDIA/nvidia-container-toolkit)
sudo zypper install nvidia-container-toolkit

# 2. Gerar a spec CDI (permite Podman rootless enxergar a GPU sem root)
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml

# 3. Conferir que o dispositivo aparece
nvidia-ctk cdi list
```

Depois, adicionar ao `ollama.container` (seção `[Container]`):

```ini
PodmanArgs=--gpus=all
```

```bash
systemctl --user daemon-reload
systemctl --user restart ollama
podman exec ollama ollama run llama3.2 --verbose   # confere "eval rate" bem mais alto
```

Continua usando a mesma imagem (`ollama/ollama`, sem sufixo) — ela já
detecta e usa a GPU sozinha se o Podman conseguir expor o dispositivo.

## Ativar GPU AMD (ROCm)

Troca de imagem (`Image=` no `.container`) pra
`docker.io/ollama/ollama:0.32.1-rocm` (mesma versão base, variante
ROCm) e expõe os dispositivos do kernel direto (sem CDI, mais simples
que o caminho NVIDIA):

```ini
Image=docker.io/ollama/ollama:0.32.1-rocm
AddDevice=/dev/kfd
AddDevice=/dev/dri
```

```bash
systemctl --user daemon-reload
systemctl --user restart ollama
```

Requer o driver ROCm instalado no host (kernel module `amdgpu` +
`rocm-smi` funcionando) — fora do escopo deste `.container`, ver
[documentação oficial da AMD](https://rocm.docs.amd.com).

## Auto-update

Sem `AutoUpdate=` — tag explícita (`0.32.1`), bump manual (regra 9 do
README raiz). Sem `HealthCmd` baseado em HTTP tradicional (a imagem não
tem `curl`/`wget`), mas o `ollama list` do healthcheck é um teste real
— daria pra habilitar `AutoUpdate=registry` com rollback funcional, mas
mantido manual como padrão do repositório.

## Backup & Recuperação

```bash
systemctl --user stop ollama
tar -czf ollama-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes ollama
systemctl --user start ollama
```

Modelos baixados costumam ser grandes (vários GB cada) — considerar
excluir da tarball de backup de rotina e só rebaixar (`ollama pull`) se
precisar restaurar, em vez de guardar cópia.

## Comandos úteis

```bash
systemctl --user status ollama
podman logs -f ollama
podman exec ollama ollama list
podman exec -it ollama ollama run <modelo>
```

## Créditos

Deploy Quadlet baseado no [Ollama](https://github.com/ollama/ollama)
(MIT).
