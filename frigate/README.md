# Frigate — Podman Quadlet (rootless)

Deploy do [Frigate](https://frigate.video) (NVR com detecção de objetos
por IA em tempo real, a partir de câmeras IP) via Podman Quadlet, usando
a imagem oficial `ghcr.io/blakeblackshear/frigate`.

**Implantado sem câmera nenhuma configurada ainda** — sobe e fica
saudável, mas não tem o que gravar/detectar até você adicionar pelo
menos uma câmera no `config.yml` (ver seção própria abaixo).

## Arquitetura

Container único. **CPU-only por decisão** — sem Coral nem GPU passados
pro container por padrão (o próprio projeto desaconselha detecção só
em CPU pra uso real, mas serve pra explorar/testar; ver "Ativar
aceleração de hardware" abaixo pra ligar depois). Por isso **sem
`--privileged`** — só é necessário quando algum dispositivo
(Coral/GPU) é passado pro container, nenhum caso aqui.

**Porta autenticada (`8971`) fala HTTPS internamente, não HTTP** —
testado na prática: a própria imagem embute um nginx com certificado
self-signed nessa porta; bater nela com HTTP puro devolve "400 The
plain HTTP request was sent to HTTPS port". Por isso o `HealthCmd`
usa `curl -k https://` (não `http://`) e o label do tsdproxy é
`.../https` no lado interno, diferente do padrão `.../http` do resto
deste repositório.

**Caminho de gravação decidido por você**, via variável do
`environment.d` (regra 19 do README raiz) — não um path fixo tipo
`%h/.config/containers/volumes/frigate/media`, porque gravação de
câmera cresce rápido e não necessariamente deve morar no mesmo disco
dos outros serviços. Ver passo 3 da instalação.

`/tmp/cache` (segmentos temporários de gravação) é `tmpfs`, não bind
mount — evita desgaste de disco com escrita constante.

## Arquivos

```
frigate-net.network   # rede bridge isolada
frigate.container       # unit principal
```

Sem `config.yml` versionado neste repositório. **Atenção**: sem nenhum
config presente, a própria imagem **gera sozinha** um
`config/config.yaml` (extensão `.yaml`, não `.yml`) no primeiro start,
com uma câmera de exemplo (`name_of_your_camera`, apontando pra um IP
fake `10.0.10.10`) — testado na prática, essa câmera fica tentando
conectar e falhando em loop nos logs (`Connection timed out` a cada
~10-20s) até ser removida/desabilitada. O passo 6 abaixo já troca esse
arquivo por um limpo (`cameras: {}`) antes de configurar a primeira
câmera de verdade.

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero

```bash
# 1. Baixar as units (sem precisar clonar o repositório)
mkdir -p ~/.config/containers/systemd/frigate
wget -P ~/.config/containers/systemd/frigate/ \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/frigate/frigate-net.network \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/frigate/frigate.container

# 2. Diretório de config — bind mount exige que já exista antes do start
mkdir -p ~/.config/containers/volumes/frigate/config

# 3. Caminho de gravação — decidir onde as gravações vão morar (disco
#    com espaço de sobra; pode ser fora de ~/.config/containers/volumes)
mkdir -p ~/.config/environment.d
cat > ~/.config/environment.d/frigate.conf <<EOF
FRIGATE_MEDIA_DIR=$HOME/frigate-media
EOF
mkdir -p "$HOME/frigate-media"
# Se preferir outro disco/mount, usar o path real ali em cima.

# 4. Aplicar a env.d nova (precisa de daemon-reload, não só reiniciar
#    o serviço — é o systemd --user que precisa reler o ambiente)
systemctl --user daemon-reload

# 5. Subir
systemctl --user start frigate

# 6. Capturar a senha do admin ANTES do restart do próximo passo —
#    testado na prática: essa mensagem só aparece no log UMA VEZ, no
#    primeiro start com o banco de usuários vazio; reiniciar depois
#    (passo 7) não recria o usuário (ele já existe, persistido no
#    volume) então a mensagem não volta a aparecer, mesmo a conta
#    continuando válida. Esperar ficar healthy antes de checar.
until podman inspect frigate --format '{{.State.Health.Status}}' 2>/dev/null | grep -qE 'healthy|unhealthy'; do sleep 3; done
podman logs frigate 2>&1 | grep -A3 "Created a default user"
# Anotar usuário/senha mostrados acima — não vão aparecer de novo depois do restart abaixo.

# 7. Limpar a câmera de exemplo que a imagem gera sozinha no primeiro
#    start (ver aviso acima) — sem isso, fica tentando conectar num IP
#    fake e poluindo os logs até você configurar uma câmera de verdade
cat > ~/.config/containers/volumes/frigate/config/config.yaml <<EOF
mqtt:
  enabled: False

cameras: {}
EOF
systemctl --user restart frigate
```

Acessar `https://<ip-do-host>:8971` (aceitar o certificado self-signed
no navegador) ou via [tsdproxy](../tsdproxy/) em
`https://frigate.<seu-tailnet>.ts.net` (aí sim com certificado válido,
o tsdproxy troca o self-signed pelo dele na borda da tailnet).

## Login (usuário gerado automaticamente)

**Sem conta padrão fixa** — a imagem cria um usuário `admin` com senha
aleatória no primeiro start, só visível no log (já capturado no passo 6
da instalação, se seguiu na ordem):

```bash
podman logs frigate 2>&1 | grep -A3 "Created a default user"
```

Trocar a senha depois de logar em Configurações → Usuários.

**Perdeu a senha** (reiniciou antes de capturar, ou já não aparece mais
no log — só sai uma vez, na primeira vez que o banco de usuários está
vazio)? Apagar o usuário do banco força a imagem a recriar um novo com
senha nova no próximo start, mesmo mecanismo do primeiro boot — testado
na prática:

```bash
systemctl --user stop frigate
podman unshare sqlite3 ~/.config/containers/volumes/frigate/config/frigate.db \
  "DELETE FROM user WHERE username='admin';"
systemctl --user start frigate
until podman inspect frigate --format '{{.State.Health.Status}}' 2>/dev/null | grep -qE 'healthy|unhealthy'; do sleep 3; done
podman logs frigate 2>&1 | grep -A3 "Created a default user"
```

## Adicionar a primeira câmera

Editar `~/.config/containers/volumes/frigate/config/config.yaml`
(criado no passo 6 da instalação — reparar na extensão `.yaml`, não
`.yml`):

```yaml
mqtt:
  enabled: False

cameras:
  frente:
    ffmpeg:
      inputs:
        - path: rtsp://usuario:senha@ip-da-camera:554/stream
          roles:
            - detect
            - record
    detect:
      width: 1280
      height: 720
    record:
      enabled: True
```

```bash
systemctl --user restart frigate
```

**Recalcular `--shm-size`** — o `128m` padrão deste deploy cobre só o
overhead do Frigate sem câmera nenhuma. Fórmula oficial por câmera
(resolução de detecção, não a de gravação):
`(largura × altura × 1.5 × 20 + 270480) / 1048576` MB, mais uns 40MB de
folga pra logs. Uma câmera 1280×720, por exemplo, fica em ~67MB — ajustar
`PodmanArgs=--shm-size=` no `.container` somando isso ao que já tiver,
depois `systemctl --user daemon-reload && systemctl --user restart
frigate`.

**Portas de restream** (`8554` RTSP, `8555` WebRTC) não vêm publicadas
por padrão — só relevantes se for usar o recurso de restream do
go2rtc embutido (assistir a câmera direto sem passar pela UI). Adicionar
`PublishPort=8554:8554` / `PublishPort=8555:8555/tcp` /
`PublishPort=8555:8555/udp` no `.container` se precisar.

## Ativar aceleração de hardware

### Coral USB

```ini
AddDevice=/dev/bus/usb:/dev/bus/usb
```

```yaml
detectors:
  coral:
    type: edgetpu
    device: usb
```

### Coral PCIe/M.2

```ini
AddDevice=/dev/apex_0:/dev/apex_0
```

```yaml
detectors:
  coral:
    type: edgetpu
    device: pci
```

### Intel GPU (OpenVINO, `/dev/dri`)

```ini
AddDevice=/dev/dri/renderD128:/dev/dri/renderD128
```

```yaml
detectors:
  ov:
    type: openvino
    device: GPU
```

### NVIDIA GPU (TensorRT) — mesma GPU do Ollama deste host

Precisa do **NVIDIA Container Toolkit** configurado pro Podman (gera a
spec CDI) — mesmo pré-requisito e mesmos passos já documentados no
[README do Ollama](../openwebui/#ativar-gpu-nvidia). Depois:

1. Trocar `Image=` pra `ghcr.io/blakeblackshear/frigate:0.16.1-tensorrt`
   (tag própria pra NVIDIA, diferente da imagem padrão usada aqui).
2. Adicionar `PodmanArgs=--gpus=all` (junto do `--shm-size=` já
   existente).
3. No `config.yml`:
   ```yaml
   detectors:
     tensorrt:
       type: tensorrt
       device: 0
   ```

```bash
systemctl --user daemon-reload
systemctl --user restart frigate
```

## Auto-update

Sem `AutoUpdate=` — tag explícita (`0.16.1`), bump manual (regra 9 do
README raiz). A imagem tem `curl`/healthcheck real — daria pra habilitar
`AutoUpdate=registry` com rollback funcional, mas gravações/config de
câmera são dado real do usuário, revisão manual antes de atualizar.

## Backup & Recuperação

```bash
systemctl --user stop frigate
tar -czf frigate-config-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes frigate
systemctl --user start frigate
```

Só o `config/` — gravações (`$FRIGATE_MEDIA_DIR`) costumam ser grandes
demais pra backup de rotina; fazer separado se precisar, ou aceitar que
são descartáveis (o valor real geralmente é a detecção em tempo real,
não o arquivo histórico).

## Comandos úteis

```bash
systemctl --user status frigate
podman logs -f frigate
podman exec frigate curl -fsSk https://127.0.0.1:8971/
```

## Créditos

Deploy Quadlet baseado no
[Frigate](https://github.com/blakeblackshear/frigate) (MIT).
