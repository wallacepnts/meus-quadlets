# netboot.xyz — Podman Quadlet (rootless)

Deploy do [netboot.xyz](https://netboot.xyz/) (menu de boot pela rede — PXE
— pra instalar/testar distros e ferramentas sem precisar de pendrive) via
Podman Quadlet, usando a imagem oficial
[netbootxyz/docker-netbootxyz](https://github.com/netbootxyz/docker-netbootxyz).

## Arquitetura

Container único (Alpine + nginx + Node.js + dnsmasq/TFTP), três serviços
internos:

- **TFTP** (`69/udp`) — serve os bootloaders (`netboot.xyz.kpxe`/`.efi`) pro
  firmware PXE dos clientes.
- **nginx** (`80` interno, `NGINX_PORT`) — serve os assets baixados
  (kernels, initrds, ISOs) que o menu carrega depois do boot inicial.
- **Web app** (`3000` interno, `WEB_APP_PORT`) — UI de configuração do
  menu/assets.

Volumes:
- `/config` — configuração persistente do menu
- `/assets` — cache de assets baixados (kernels, initrds) — opcional, sem
  ele os assets são baixados de novo a cada boot

**Importante**: TFTP/nginx são pra clientes de PXE na **LAN**, antes de
terem sistema operacional — não são nós Tailscale, então não fazem parte
da tailnet. O [tsdproxy](../tsdproxy/) aqui só publica a UI web de
configuração (porta 3000); as portas 69 e 8089 precisam estar acessíveis
direto no IP da LAN do host.

## Arquivos

```
quadlet/
└── netbootxyz.container   # unit principal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando
- **Porta 69/UDP é privilegiada (<1024)** — rootless não consegue publicar
  sem ajustar o piso de portas não-privilegiadas do kernel:
  ```bash
  sudo sysctl -w net.ipv4.ip_unprivileged_port_start=69
  ```
  Testado na prática: sem isso, `podman run -p 69:69/udp` falha com
  `pasta failed ... Listen failed for HOST UDP port */69: Permission
  denied`. Pra persistir entre reboots:
  ```bash
  echo 'net.ipv4.ip_unprivileged_port_start=69' | sudo tee /etc/sysctl.d/99-netbootxyz-tftp.conf
  ```
- **DHCP externo já configurado** — este container **não** provê DHCP,
  só TFTP/HTTP. O servidor DHCP da rede (roteador, pfSense, dnsmasq
  próprio etc.) precisa apontar os clientes de PXE pra este host:
  - Option 66 (`next-server`): IP deste host na LAN
  - Option 67 (`filename`): `netboot.xyz.kpxe` (BIOS) ou
    `netboot.xyz.efi` (UEFI) — o próprio painel web mostra o valor exato
  - Sem esse passo, os clientes nunca chegam a fazer a requisição TFTP —
    não tem log de erro no container, o pedido simplesmente nunca chega.
- Porta 69/UDP e 8089/TCP liberadas no firewall do host **pra LAN**, não
  só pra tailnet (regra 10 do README raiz — `PublishPort=` não abre
  firewall sozinho).

## Instalação do zero

```bash
# 1. Copiar a unit
mkdir -p ~/.config/containers/systemd
cp quadlet/netbootxyz.container ~/.config/containers/systemd/

# 2. Diretórios de dados — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/netbootxyz/{config,assets}

# 3. Env não-secreto (todas as variáveis são opcionais, ver .env.example)
mkdir -p ~/.config/containers/env
cp .env.example ~/.config/containers/env/netbootxyz.env

# 4. Subir
systemctl --user daemon-reload
systemctl --user start netbootxyz
```

UI de configuração via [tsdproxy](../tsdproxy/) (tailnet) em
`https://netbootxyz.<seu-tailnet>.ts.net`, ou local em
`http://localhost:8088`. Os assets ficam em `http://<ip-da-lan>:8089/`
(usado internamente pelo menu, não precisa acessar direto).

Depois de configurar o DHCP (ver Pré-requisitos), um cliente de PXE na
mesma LAN já cai no menu do netboot.xyz ao dar boot.

## Auto-update

Sem `AutoUpdate=` — tag explícita (`0.7.6-nbxyz23`), bump manual (regra 9
do README raiz). A imagem tem `curl`/healthcheck real (daria pra habilitar
com rollback de verdade), mas o próprio boot loader/menu (`/config`) é
sensível a mudanças de versão do webapp — prefiro conferir o changelog
antes de trocar de tag. `wud.watch=true` fica ligado só pra visibilidade
passiva (ver [wud](../wud/)).

Vale notar: `MENU_VERSION` (se definido) e o conteúdo de `/assets` são
atualizados independente da tag da imagem — o menu builder do
netboot.xyz busca a versão mais recente do menu a cada start por padrão,
isso não é controlado pelo `AutoUpdate=` do Podman.

## Backup & Recuperação

```bash
systemctl --user stop netbootxyz
tar -czf netbootxyz-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes netbootxyz
systemctl --user start netbootxyz
```

`/assets` é só cache (recriável baixando de novo) — dá pra excluir do
backup se quiser algo menor, mantendo só `/config`.

## Comandos úteis

```bash
systemctl --user status netbootxyz
podman logs -f netbootxyz
```

## Créditos

Deploy Quadlet usando a imagem oficial
[netbootxyz/docker-netbootxyz](https://github.com/netbootxyz/docker-netbootxyz)
(MIT), do projeto [netboot.xyz](https://netboot.xyz/).
