# Monica — Podman Quadlet (rootless)

Deploy do [Monica](https://www.monicahq.com) (CRM pessoal — histórico de
relacionamentos, contatos, lembretes) via Podman Quadlet, usando a
imagem `ghcr.io/monicahq/monica-next` (v5, com SQLite).

## Tag flutuante — exceção consciente à regra 9

**Sem tag fixa** — diferente de todo o resto do repositório. A v5 (a
versão com SQLite, mais simples de manter aqui) só publica essa imagem
como `:main`, sem nenhuma tag versionada. Testado na prática antes de
decidir: nenhuma tag do `monicahq/monica` no Docker Hub puxa deste
host — nem as da v5 (`5.0.0-beta.5-apache` etc.) nem as da v4 estável
(`4.1.2-apache`), erro de acesso em todas, parece o repositório inteiro
inacessível, não é limitação específica de versão. `ghcr.io/monicahq/monica-next:main`
foi a única imagem que realmente funcionou.

**Risco aceito, documentado**: `:main` é a branch de desenvolvimento de
software pré-1.0 — pode trazer migração de banco quebrada ou mudança de
schema sem aviso a qualquer restart/pull. Mesmo padrão de exceção já
usado pro dispatcharr/gluetun no [media-stack](../media-stack/). Sem
`wud.watch=true` de propósito — tag flutuante, o WUD não teria o que
comparar.

Se/quando a v5 tiver release estável com tag fixa (ou se o Docker Hub
voltar a ficar acessível), trocar `Image=` e reavaliar essa seção.

## Arquitetura

Container único. **SQLite**, não MySQL/MariaDB (só a v4, antiga, exige
banco externo) — mais simples, dado real do usuário de qualquer forma
não justifica um Postgres/MySQL à parte aqui.

**`APP_URL` precisa ser o domínio real, não o placeholder do
`.env.example`** — testado na prática: deixar `<seu-tailnet>` literal
não quebra o container (sobe "saudável" normal), mas a UI não carrega
no navegador via tsdproxy — toda URL de asset (JS/CSS) e rota interna é
gerada como `http://`, mesmo a página sendo servida em `https://` (o
tsdproxy termina TLS antes de chegar no container), e o navegador
bloqueia isso como "mixed content" silenciosamente. Editar o
`APP_URL` pro domínio real antes do primeiro start evita o problema.

**A variável certa é `APP_TRUSTED_PROXIES`, não `TRUSTED_PROXIES`** —
essa segunda parece óbvia mas não existe nessa imagem (é
`config/trustedproxy.php` → `env('APP_TRUSTED_PROXIES')`); sem ela
configurada, o Laravel não confia no cabeçalho `X-Forwarded-Proto` do
tsdproxy e acaba gerando as URLs erradas mesmo com `APP_URL` certo.

**Banco redirecionado pra dentro do volume persistido** — por padrão a
imagem grava o SQLite em `database/database.sqlite`, **fora** de
`storage/` (o próprio `entrypoint.sh` da imagem avisa: "make sure it
will be saved in a persistent volume"). `DB_DATABASE` no `.container`
redireciona pra `storage/database.sqlite`, dentro do único volume
montado — sem isso, o CRM inteiro se perde a cada recriação do
container.

**`APP_KEY` como secret via `type=env`, não `target=APP_KEY` sem
`type=env`** — testado na prática: a imagem suporta ler secret de
arquivo, mas só via uma variável `APP_KEY_FILE` apontando pro caminho
(convenção própria dela) — montar o secret como arquivo simples não
é o suficiente, ela ignora e gera uma chave nova sozinha. Injetar como
env var direto é mais simples e funciona de primeira. Sem essa chave
fixa, uma nova é gerada a cada start (não persiste em lugar nenhum),
invalidando sessões e qualquer campo criptografado no banco.

Roda como root internamente (Apache) — sem `UserNS=keep-id`, o
`entrypoint.sh` já faz `chown -R www-data:www-data` em `storage/`
sozinho no start.

## Arquivos

```
monica-net.network   # rede bridge isolada
monica.container       # unit principal
```

## Pré-requisitos

- Podman rootless com systemd `--user` funcionando

## Instalação do zero

```bash
# 1. Baixar as units (sem precisar clonar o repositório)
mkdir -p ~/.config/containers/systemd/monica
wget -P ~/.config/containers/systemd/monica/ \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/monica/monica-net.network \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/monica/monica.container

# 2. Diretório de dados — bind mount exige que já exista antes do start
mkdir -p ~/.config/containers/volumes/monica/storage

# 3. Env não-secreto — baixar o exemplo e EDITAR o APP_URL (trocar
#    "<seu-tailnet>" pelo domínio real, ver abaixo) antes de subir
mkdir -p ~/.config/containers/env
wget -O ~/.config/containers/env/monica.env \
  https://raw.githubusercontent.com/wallacepnts/meus-quadlets/main/monica/.env.example

# 4. Secret — APP_KEY (formato "base64:" + 32 bytes aleatórios em base64,
#    igual ao que o próprio `artisan key:generate` produziria)
mkdir -p ~/.config/containers/secrets/monica
python3 -c "
import base64, os
print(f'base64:{base64.b64encode(os.urandom(32)).decode()}', end='')
" > ~/.config/containers/secrets/monica/app-key.txt
chmod 600 ~/.config/containers/secrets/monica/app-key.txt
podman secret create monica-app-key ~/.config/containers/secrets/monica/app-key.txt

# 5. Subir
systemctl --user daemon-reload
systemctl --user start monica
```

Acessar `http://<ip-do-host>:9092` (ou via [tsdproxy](../tsdproxy/) em
`https://monica.<seu-tailnet>.ts.net`) e criar a conta no primeiro
acesso (`/register`). **Sem conta padrão nessa imagem** (diferente do
[Mealie](../mealie/)) — o cadastro é o único jeito de entrar.

**Confirmação de e-mail obrigatória** — com `MAIL_MAILER=log` (padrão
deste `.env.example`), o e-mail de confirmação não é enviado de
verdade, fica escrito nos logs do container:

```bash
podman logs monica 2>&1 | grep -A5 "verify\|reset-password"
```

O link de confirmação aparece ali (`.../email/verify/<id>/<hash>?...`)
— abrir ele completa o cadastro. Mesmo caminho serve pra recuperação de
senha depois. Configurar SMTP de verdade (seção abaixo) evita precisar
caçar link no log toda vez.

## Configurar SMTP de verdade (opcional)

Trocar no `monica.env`:

```ini
MAIL_MAILER=smtp
MAIL_HOST=smtp.exemplo.com
MAIL_PORT=587
MAIL_ENCRYPTION=tls
MAIL_USERNAME=seu-usuario
MAIL_FROM_ADDRESS=monica@exemplo.com
MAIL_FROM_NAME=Monica
```

A senha do SMTP **não** vai no `.env` — como secret, injetada via
`MAIL_PASSWORD_FILE` (suportado nativamente pelo `entrypoint.sh` da
imagem, mesma convenção do `APP_KEY_FILE` documentada acima, mas aqui
funciona porque não estamos usando o atalho `type=env` — se preferir
`type=env,target=MAIL_PASSWORD` direto, também funciona, mais simples):

```bash
mkdir -p ~/.config/containers/secrets/monica
echo -n "senha-do-smtp" > ~/.config/containers/secrets/monica/mail-password.txt
chmod 600 ~/.config/containers/secrets/monica/mail-password.txt
podman secret create monica-mail-password \
  ~/.config/containers/secrets/monica/mail-password.txt
```

No `monica.container`, adicionar junto do `Secret=monica-app-key,...`
já existente:

```ini
Secret=monica-mail-password,type=env,target=MAIL_PASSWORD
```

```bash
systemctl --user daemon-reload
systemctl --user restart monica
```

## Auto-update

**Não aplicável** — sem tag fixa não tem o que o Podman comparar contra
o registry pra decidir se atualiza (`AutoUpdate=registry` precisa de
imagem totalmente qualificada, tag flutuante inclusa, mas não faria
sentido nenhum revisar automaticamente algo que já é branch de
desenvolvimento). Atualizar aqui é sempre manual: `podman pull` +
restart, ciente do risco descrito acima.

## Backup & Recuperação

```bash
systemctl --user stop monica
tar -czf monica-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C ~/.config/containers/volumes monica
systemctl --user start monica
```

`~/.config/containers/secrets/monica/app-key.txt` também precisa de
backup separado — sem ela, o banco restaurado fica com campos
criptografados ilegíveis (a chave usada pra criptografar era outra).

## Comandos úteis

```bash
systemctl --user status monica
podman logs -f monica
podman exec monica curl -fsS http://127.0.0.1:80/login
```

## Créditos

Deploy Quadlet baseado no [Monica](https://github.com/monicahq/monica)
(AGPL-3.0).
