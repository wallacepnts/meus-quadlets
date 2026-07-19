# Open WebUI + Ollama — Podman Quadlet (rootless)

Deploy do [Open WebUI](https://github.com/open-webui/open-webui)
(interface de chat web pra LLMs) junto do [Ollama](https://ollama.com)
(servidor de LLMs locais que ele usa como backend), via Podman Quadlet —
migrado do
[`docker-compose.yaml`](https://github.com/open-webui/open-webui/blob/main/docker-compose.yaml)
oficial do projeto (a variante com os dois serviços separados, não a
imagem `:ollama` que embute os dois num container só — ver comparação
abaixo).

## Comparação das variantes de imagem do Open WebUI

| Tag | O que é | Por que (não) usar aqui |
| --- | --- | --- |
| **`:main`** (usada aqui) | Só o Open WebUI, fala com um Ollama externo via `OLLAMA_BASE_URL` | Combina com o `ollama.container` deste diretório — dois containers, cada um com seu próprio ciclo de vida/update/log |
| `:ollama` | Open WebUI **+ Ollama embutido no mesmo container** | O compose oficial do projeto (linkado acima) já não usa essa variante — prefere dois serviços separados, mesma escolha feita aqui. Um container só dificulta atualizar/reiniciar um sem o outro, e mistura os logs dos dois |
| `:cuda` | Mesma base do `:main`, com CUDA Toolkit embutido pra acelerar por GPU as tarefas *internas* do próprio Open WebUI (embedding local, Whisper de voz-pra-texto, reranking) — **não tem relação com a GPU do Ollama** | Este host está CPU-only por decisão (sem `nvidia-container-toolkit`/CDI configurado — ver "Ativar GPU NVIDIA" abaixo). Se a GPU for ativada, essa tag passa a valer a pena pras tarefas de embedding/voz — trocar `Image=` no `openwebui.container` pra `ghcr.io/open-webui/open-webui:v0.10.2-cuda` e adicionar `PodmanArgs=--gpus=all` |
| `:dev` | Build da branch principal, sem tag de release | Fora de cogitação pra uso doméstico estável (regra 9 do README raiz) |

## Arquitetura

Dois containers na mesma rede (`openwebui-net.network`):

- `ollama` — o servidor de LLMs em si, API HTTP na porta `11434`
  (publicada no host também, pra uso direto via `podman exec ollama
  ollama run <modelo>` ou API sem passar pelo Open WebUI).
- `openwebui` — a interface web, `Requires=`/`After=ollama.service` no
  `[Unit]` garante que o Ollama já esteja no ar antes dele tentar
  falar com `http://ollama:11434` (nome resolvido via DNS interno do
  Podman, os dois na mesma rede).

**CPU-only por padrão** — sem GPU, roda em qualquer host, mais lento
pra modelos grandes. Ver "Ativar GPU NVIDIA"/"Ativar GPU AMD (ROCm)"
abaixo.

Primeiro start do Open WebUI baixa um modelo de embedding padrão
(`sentence-transformers/all-MiniLM-L6-v2`, usado pra RAG/busca
semântica) direto do Hugging Face — testado na prática, isso sozinho já
passa de 60s; por isso o `HealthStartPeriod`/`TimeoutStartSec` desse
`.container` são generosos.

`WEBUI_SECRET_KEY` como secret (regra 2/15 do README raiz) — sem ele
fixo, o Open WebUI gera uma chave nova a cada restart do container e
invalida a sessão de todo mundo logado (diferente do compose oficial,
que deixa em branco).

## Arquivos

```
openwebui-net.network   # rede bridge compartilhada pelos dois
ollama.container        # backend — servidor de LLMs
openwebui.container     # interface web
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero (CPU-only)

```bash
# 1. Baixar as units (sem precisar clonar o repositório)
mkdir -p ~/.config/containers/systemd
wget -P ~/.config/containers/systemd/ \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/openwebui/openwebui-net.network \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/openwebui/ollama.container \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/openwebui/openwebui.container

# 2. Diretórios de dados — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/openwebui/{ollama,webui}

# 3. Env não-secreto (Open WebUI)
mkdir -p ~/.config/containers/env
wget -O ~/.config/containers/env/openwebui.env \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/openwebui/.env.example

# 4. Secret — chave usada pra assinar sessão de login do Open WebUI
mkdir -p ~/.config/containers/secrets/openwebui
python3 -c "import secrets; print(secrets.token_hex(32))" \
  > ~/.config/containers/secrets/openwebui/secret-key.txt
chmod 600 ~/.config/containers/secrets/openwebui/secret-key.txt
podman secret create openwebui-secret-key \
  ~/.config/containers/secrets/openwebui/secret-key.txt

# 5. Subir (Ollama primeiro, Open WebUI já sobe ele sozinho via Requires=,
#    mas dá pra fazer os dois num só start pelo principal)
systemctl --user daemon-reload
systemctl --user start openwebui
```

Baixar um modelo e testar direto pelo Ollama (opcional, o Open WebUI
também baixa modelo pela própria UI):

```bash
podman exec -it ollama ollama pull llama3.2
```

Acessar o Open WebUI em `http://<ip-do-host>:3003` (ou via
[tsdproxy](../tsdproxy/) em `https://openwebui.<seu-tailnet>.ts.net`) e
criar a conta no primeiro acesso — **o primeiro usuário a se cadastrar
vira admin automaticamente**. Depois de criar essa conta, desligar
cadastro aberto em Painel Admin → Configurações → Geral → "Habilitar
Novos Cadastros", senão qualquer um que alcance a URL consegue criar
conta própria.

API do Ollama sozinha (sem passar pelo Open WebUI) em
`http://<ip-do-host>:11434`.

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

Depois, adicionar ao **`ollama.container`** (seção `[Container]`) —
acelera o próprio Ollama, o principal consumidor de GPU do par:

```ini
PodmanArgs=--gpus=all
```

Opcionalmente, o **`openwebui.container`** também pode usar GPU pras
tarefas internas dele (embedding local, Whisper) — nesse caso trocar
`Image=` pra `ghcr.io/open-webui/open-webui:v0.10.2-cuda` e adicionar o
mesmo `PodmanArgs=--gpus=all`.

```bash
systemctl --user daemon-reload
systemctl --user restart ollama openwebui
podman exec ollama ollama run llama3.2 --verbose   # confere "eval rate" bem mais alto
```

Continua usando a mesma imagem base do Ollama (`ollama/ollama`, sem
sufixo) — ela já detecta e usa a GPU sozinha se o Podman conseguir
expor o dispositivo.

## Ativar GPU AMD (ROCm)

Troca de imagem no **`ollama.container`** pra
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

Sem `AutoUpdate=` nos dois — tags explícitas (`0.32.1`/`v0.10.2`), bump
manual (regra 9 do README raiz). Ambas as imagens têm healthcheck real
(`ollama list`/endpoint `/health`, testados na prática) — daria pra
habilitar `AutoUpdate=registry` com rollback funcional em qualquer um
dos dois, mas mantido manual como padrão do repositório.

## Backup & Recuperação

```bash
systemctl --user stop openwebui ollama
tar -czf openwebui-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes openwebui
systemctl --user start ollama openwebui
```

Modelos baixados (`openwebui/ollama/`) costumam ser grandes (vários GB
cada) — considerar excluir da tarball de backup de rotina e só rebaixar
(`ollama pull`) se precisar restaurar, em vez de guardar cópia.

## Comandos úteis

```bash
systemctl --user status ollama openwebui
podman logs -f ollama
podman logs -f openwebui
podman exec ollama ollama list
podman exec -it ollama ollama run <modelo>
podman exec openwebui curl -fsS http://127.0.0.1:8080/health
```

## Créditos

Deploy Quadlet baseado no [Ollama](https://github.com/ollama/ollama)
(MIT) e no [Open WebUI](https://github.com/open-webui/open-webui)
(BSD-3-Clause).
