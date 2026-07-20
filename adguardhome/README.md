# AdGuard Home — Podman Quadlet (rootless)

Deploy do [AdGuard Home](https://github.com/AdguardTeam/AdGuardHome) (DNS
recursivo com bloqueio de anúncios/rastreadores pra toda a rede) via
Podman Quadlet, seguindo o
[guia oficial de Docker](https://github.com/AdguardTeam/AdGuardHome/wiki/Docker).

## Arquitetura

Container único, roda como root internamente (padrão da própria imagem —
precisa disso pra abrir a porta 53 dentro do namespace de rede dele; não é
o root real do host, ver seção sobre porta privilegiada). Rede **bridge**,
não `host` (o wiki oficial recomenda `host` só pra DHCP ou pra ver o IP
real de cada cliente nas estatísticas — mesma troca consciente já feita
pro [Syncthing](../syncthing/)/Jellyfin: sem DHCP embutido e as
estatísticas por cliente mostram o IP do gateway da rede bridge do
Podman, não o IP de cada dispositivo da LAN; bloqueio de anúncios pra
rede inteira funciona normal, é o uso principal deste deploy).

Dois volumes: `conf` (config gerada no assistente de instalação,
`AdGuardHome.yaml`) e `work` (dados de runtime — filtros baixados,
estatísticas, logs de consulta).

**DNS na porta `5335`, não na `53` padrão** — decisão consciente deste
deploy: rootless Podman não publica portas privilegiadas (<1024) sem
mexer num sysctl do host (ver seção própria mais abaixo), e essa mudança
foi propositalmente deixada de fora do padrão pra não alterar
comportamento do host só por causa deste serviço. Efeito prático: **este
deploy, do jeito que está, não serve como resolver de DNS da rede/LAN** —
roteador e a maioria dos sistemas operacionais só falam DNS na porta 53,
sem opção de porta customizada. Serve pra testar/usar manualmente (`dig
@<ip-do-host> -p 5335 exemplo.com`, ou apps que aceitem porta
customizada). Quem quiser o uso completo (DNS de toda a rede, apontando o
roteador pra cá) faz a mudança opcional descrita em "Usar a porta 53
padrão de DNS" abaixo.

## Arquivos

```
adguardhome-net.network   # rede bridge isolada
adguardhome.container     # unit principal
```

Sem `.env.example` — a imagem não usa variáveis de ambiente pra
configuração (tudo é feito pelo assistente web na primeira execução, ver
abaixo).

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero

```bash
# 1. Baixar as units (sem precisar clonar o repositório)
mkdir -p ~/.config/containers/systemd/adguardhome
wget -P ~/.config/containers/systemd/adguardhome/ \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/adguardhome/adguardhome-net.network \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/adguardhome/adguardhome.container

# 2. Diretórios de dados — bind mount exige que já existam antes do start
mkdir -p ~/.config/containers/volumes/adguardhome/{conf,work}

# 3. Subir
systemctl --user daemon-reload
systemctl --user start adguardhome
```

Acessar o assistente de instalação em `http://<ip-do-host>:3002` (ou via
[tsdproxy](../tsdproxy/) em `https://adguardhome.<seu-tailnet>.ts.net`,
só pra administração). No assistente, **manter a porta da interface admin
em `3000`** (a padrão sugerida) — o `HealthCmd` deste `.container` testa
exatamente essa porta por dentro do container; mudar pra outra porta ali
quebra o healthcheck. A porta DNS interna pode ficar em `53` normalmente
(padrão sugerido) — quem muda é só o mapeamento externo, pro host expor
em `5335` em vez de `53` (ver "Arquitetura" acima).

## Testar/usar manualmente (porta 5335)

```bash
dig @<ip-do-host> -p 5335 exemplo.com
```

Pra usar de verdade como DNS de um dispositivo específico, configurar
manualmente nele um resolver com porta customizada (a maioria dos
sistemas operacionais/roteadores não deixa escolher porta no campo de
DNS padrão — funciona em apps/ferramentas que aceitem `host:porta`
explícito).

## Usar a porta 53 padrão de DNS (opcional, muda escopo do host)

Pra usar como resolver de verdade da rede/LAN inteira (apontando o
roteador ou os dispositivos direto, sem porta customizada), duas mudanças
opcionais:

**1. Liberar bind de porta privilegiada pro Podman rootless** — quem faz
o bind da porta 53 no host é um processo do próprio usuário
(`rootlessport`), sem `CAP_NET_BIND_SERVICE` por padrão:

```bash
echo "net.ipv4.ip_unprivileged_port_start=53" | sudo tee /etc/sysctl.d/99-adguardhome-port53.conf
sudo sysctl --system
```

Mudança em nível de host (libera bind sem privilégio pras portas 53-1023
pra **qualquer** processo do usuário, não só este container) — reversível
apagando o arquivo e rodando `sudo sysctl --system` de novo.

**2. Trocar o mapeamento de porta** no `adguardhome.container` — nas duas
linhas `PublishPort=5335:53/...`, trocar o `5335` por `53`:

```ini
PublishPort=53:53/tcp
PublishPort=53:53/udp
```

```bash
systemctl --user daemon-reload
systemctl --user restart adguardhome
```

Depois, apontar o DNS dos dispositivos (individualmente ou, melhor, nas
configurações de DHCP do roteador, pra valer pra rede inteira) pro **IP
do host** (não do container) na porta 53 — ex.: `192.168.1.X`. Como a
rede é bridge (não `host`), o AdGuard só vê o IP do gateway da rede
Podman como "cliente" de cada consulta, não o IP real de cada
dispositivo — filtros globais funcionam normalmente, só as estatísticas
por cliente/regras por dispositivo ficam sem efeito prático nesse modo.

## Auto-update

Sem `AutoUpdate=` — tag explícita (`v0.107.78`), bump manual (regra 9 do
README raiz). DNS é infraestrutura crítica da rede inteira (se cair,
ninguém resolve nome nenhum, mesmo raciocínio do
[ownCloud](../owncloud/)/[Radicale](../radicale/) pra dado de usuário) —
revisão manual antes de atualizar, apesar da imagem ter `wget` disponível
pra um `HealthCmd` de verdade (daria pra habilitar rollback automático se
quiser assumir esse risco).

## Backup & Recuperação

```bash
systemctl --user stop adguardhome
tar -czf adguardhome-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes adguardhome
systemctl --user start adguardhome
```

## Comandos úteis

```bash
systemctl --user status adguardhome
podman logs -f adguardhome
podman exec adguardhome wget -qO- http://127.0.0.1:3000/
```

## Créditos

Deploy Quadlet baseado no
[AdGuard Home](https://github.com/AdguardTeam/AdGuardHome) (GPL-3.0).
