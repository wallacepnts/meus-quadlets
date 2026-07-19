# Open WebUI — Podman Quadlet (rootless)

Deploy do [Open WebUI](https://github.com/open-webui/open-webui)
(interface de chat web pra LLMs — Ollama local ou qualquer API
compatível com OpenAI) via Podman Quadlet.

Depende do [Ollama](../ollama/) já implantado neste repositório — subir
esse primeiro.

## Comparação das variantes de imagem (tags)

| Tag | O que é | Por que (não) usar aqui |
| --- | --- | --- |
| **`:main`** (usada aqui) | Só o Open WebUI, sem nada embutido — fala com um Ollama (ou outra API) externo via `OLLAMA_BASE_URL` | Já temos um [Ollama](../ollama/) próprio rodando em container separado — não faz sentido duplicar |
| `:ollama` | Open WebUI **+ Ollama embutido no mesmo container** (`ollama:/root/.ollama` junto) | Serve pra quem quer um único comando/container pra tudo; aqui geraria dois Ollamas rodando (o dedicado deste repo + o embutido), desperdício de RAM/disco |
| `:cuda` | Mesma base do `:main`, mas com CUDA Toolkit embutido pra acelerar por GPU as tarefas *internas* do próprio Open WebUI (embedding local, Whisper de voz-pra-texto, reranking) — **não tem relação com a GPU do Ollama**, que é um serviço à parte | Este host está CPU-only por decisão (ver [Ollama](../ollama/) — sem `nvidia-container-toolkit`/CDI configurado ainda); trocar pra essa tag sem a GPU exposta ao container não muda nada, só infla a imagem à toa. Se a GPU NVIDIA for ativada no host (seção correspondente no README do Ollama), essa tag passa a valer a pena pras tarefas de embedding/voz — trocar `Image=` pra `ghcr.io/open-webui/open-webui:v0.10.2-cuda` e adicionar `PodmanArgs=--gpus=all` |
| `:dev` | Build da branch principal, sem tag de release — features de ponta, quebra sem aviso | Fora de cogitação pra uso doméstico estável (mesmo raciocínio de tag flutuante evitada em todo o repositório, regra 9) |

## Arquitetura

Container único. **Reaproveita a rede do Ollama** (`ollama-net`, definida
em [`../ollama/`](../ollama/)) em vez de criar uma rede própria — assim
os dois containers se enxergam pelo nome via DNS interno do Podman
(`OLLAMA_BASE_URL=http://ollama:11434`), sem precisar publicar a porta
do Ollama pra fora nem duplicar configuração de rede. `Requires=` +
`After=ollama.service` no `[Unit]` garante que o Ollama já esteja no ar
antes do Open WebUI tentar falar com ele.

Primeiro start baixa um modelo de embedding padrão
(`sentence-transformers/all-MiniLM-L6-v2`, usado pra RAG/busca
semântica) direto do Hugging Face — testado na prática, isso sozinho já
passa de 60s; por isso o `HealthStartPeriod`/`TimeoutStartSec` deste
`.container` são generosos.

`WEBUI_SECRET_KEY` como secret (regra 2/15 do README raiz) — sem ele
fixo, o Open WebUI gera uma chave nova a cada restart do container e
invalida a sessão de todo mundo logado.

## Arquivos

```
openwebui.container   # unit principal
```

Sem `.network` próprio — usa a `ollama-net.network` já existente (ver
"Arquitetura" acima).

## Pré-requisitos

- [Ollama](../ollama/) já implantado e rodando neste host

## Instalação do zero

```bash
# 1. Baixar a unit (sem precisar clonar o repositório)
mkdir -p ~/.config/containers/systemd
wget -P ~/.config/containers/systemd/ \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/openwebui/openwebui.container

# 2. Diretório de dados — bind mount exige que já exista antes do start
mkdir -p ~/.config/containers/volumes/openwebui/data

# 3. Env não-secreto
mkdir -p ~/.config/containers/env
wget -O ~/.config/containers/env/openwebui.env \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/openwebui/.env.example

# 4. Secret — chave usada pra assinar sessão de login
mkdir -p ~/.config/containers/secrets/openwebui
python3 -c "import secrets; print(secrets.token_hex(32))" \
  > ~/.config/containers/secrets/openwebui/secret-key.txt
chmod 600 ~/.config/containers/secrets/openwebui/secret-key.txt
podman secret create openwebui-secret-key \
  ~/.config/containers/secrets/openwebui/secret-key.txt

# 5. Subir
systemctl --user daemon-reload
systemctl --user start openwebui
```

Acessar em `http://<ip-do-host>:3003` (ou via [tsdproxy](../tsdproxy/)
em `https://openwebui.<seu-tailnet>.ts.net`) e criar a conta no primeiro
acesso — **o primeiro usuário a se cadastrar vira admin automaticamente**.
Depois de criar essa conta, desligar cadastro aberto em
Painel Admin → Configurações → Geral → "Habilitar Novos Cadastros", senão
qualquer um que alcance a URL consegue criar conta própria.

## Auto-update

Sem `AutoUpdate=` — tag explícita (`v0.10.2`), bump manual (regra 9 do
README raiz). A imagem tem `curl`/healthcheck real (endpoint próprio
`/health`, testado na prática) — daria pra habilitar `AutoUpdate=registry`
com rollback funcional, mas mantido manual como padrão do repositório.

## Backup & Recuperação

```bash
systemctl --user stop openwebui
tar -czf openwebui-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes openwebui
systemctl --user start openwebui
```

## Comandos úteis

```bash
systemctl --user status openwebui
podman logs -f openwebui
podman exec openwebui curl -fsS http://127.0.0.1:8080/health
```

## Créditos

Deploy Quadlet baseado no
[Open WebUI](https://github.com/open-webui/open-webui) (BSD-3-Clause).
