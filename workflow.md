# 1

В Compose по умолчанию пути идут к server/skeleton и server/modules. На VPS можно клонировать именно туда и запускать docker compose up --build.

server/modules монтируется в web и orchestrator, поэтому исходники каталога не вшиты в их образы. Серверный список ограничен base и spaceTW. При регистрации выбранные исходники устанавливаются в пользовательский каталог, а затем монтируются в его worker.

## подготовка сервера

```sh
mkdir ubot
cd ubot/
git clone git@github.com:ant-Visor/server.git
cd server/
git clone git@github.com:ant-Visor/skeleton.git
# git clone git@github.com:ant-Visor/modules.git
ssh-keygen -t ed25519 -f ~/.ssh/modules_deploy -C "server-modules" -N ""
cat ~/.ssh/modules_deploy.pub
vim ~/.ssh/services/gh_ub_modules.conf
: "
Host github-modules
  HostName github.com
  User git
  IdentityFile ~/.ssh/modules_deploy
  IdentitiesOnly yes
# "
ssh -T git@github-modules
git clone git@github-modules:ant-Visor/modules.git
```

## Configs

```bash
cp cp .env{.example,}
vim .env
docker compose up --build
```

## DNS

### Получить DNS

Бесплатно на <https://www.duckdns.org/domains>

### Открыть порты фаервола

#### В консоли Oracle Cloud

Открой Compute → Instances → твоя VM. В разделе Attached VNICs открой основной сетевой интерфейс (Primary VNIC).
Перейди по ссылке Subnet, затем открой Security Lists и выбери список, привязанный к этой подсети.
Нажми Add Ingress Rules и добавь два правила:

| Поле | Правило для HTTP | Правило для HTTPS |
| --- | --- | --- |
| Stateless | Не отмечать | Не отмечать |
| Source Type | CIDR | CIDR |
| Source CIDR | 0.0.0.0/0 | 0.0.0.0/0 |
| IP Protocol | TCP | TCP |
| Source Port Range | Оставить пустым | Оставить пустым |
| Destination Port Range | 80 | 443 |

```sh
sudo iptables -S INPUT
sudo iptables -I INPUT 1 -p tcp -m multiport --dports 80,443 -j ACCEPT
sudo iptables -L INPUT -n -v --line-numbers
```

```note
Chain INPUT (policy ACCEPT 0 packets, 0 bytes)
num   pkts bytes target     prot opt in     out     source               destination
1        0     0 ACCEPT     6    --  *      *       0.0.0.0/0            0.0.0.0/0            multiport dports 80,443
2     493K  120M ACCEPT     0    --  *      *       0.0.0.0/0            0.0.0.0/0            state RELATED,ESTABLISHED
3        0     0 ACCEPT     1    --  *      *       0.0.0.0/0            0.0.0.0/0
4    14697 1428K ACCEPT     0    --  lo     *       0.0.0.0/0            0.0.0.0/0
5     3687  194K ACCEPT     6    --  *      *       0.0.0.0/0            0.0.0.0/0            state NEW tcp dpt:22
6       69  3002 REJECT     0    --  *      *
```

### Запустить Caddy, он получит сертификаты

```bash
docker compose --profile https up -d caddy
docker compose --profile https ps
docker compose --profile https logs --tail=80 caddy
```

### при смене данных

Не публикуй .env целиком: в нём также есть TELEGRAM_API_HASH. После замены значений примени их командой docker compose --profile https up -d, затем отправь боту новый /start, чтобы получить актуальную кнопку Mini App.



Разреши входящий TCP на 80 и 443 в Oracle Cloud: в Security List подсети или NSG сетевого интерфейса VPS. На Ubuntu ufw не установлен, а в iptables цепочка INPUT заканчивается REJECT и явно разрешает только SSH из новых TCP-подключений. Если после запуска Caddy снаружи всё ещё будет таймаут, проверь и правила Docker-маршрутизации FORWARD/DOCKER-USER: опубликованные порты контейнеров не обязательно проходят через INPUT. Не отключай firewall целиком и не открывай наружу 8080 или 8090.
Активируй HTTPS-профиль. Из каталога server на VPS:
docker compose --profile https up -d
docker compose --profile https ps
docker compose --profile https logs --tail=80 caddy
В ps должен появиться Caddy с опубликованным 443. Затем с другого устройства или сети проверь curl -fsS https://ub.example.com/health. Когда он вернёт {"status":"ok"} без отключения проверки TLS, отправь боту новый /start, чтобы получить кнопку с новым URL.
Ещё две настройки перед регистрацией: HOST_USERS_DIR=./users не вызывает этот таймаут, но позже оркестратор отклонит относительный путь. Из каталога server выполни realpath users и укажи результат в .env. Также замени ORCHESTRATOR_TOKEN=replace-with-a-long-random-value на случайный секрет.



## we

На VPS из каталога /home/ubuntu/ubot/server:

```bash
docker rm -f ub-user-295750588
docker compose --profile https down
docker ps -a --filter label=com.docker.compose.project=server
```

Здесь лучше не добавлять -v: так сохранятся тома Caddy с уже полученным TLS-сертификатом. Сессия, настройки и БД пользователя лежат на хосте в users/, поэтому удаление контейнера их тоже не сотрёт. Отдельный legasy-bot-1 не трогай: он относится к другому проекту.

После остановки обнови все три репозитория, поскольку git pull в server не обновляет вложенные клоны:

```bash
git pull --ff-only
git -C skeleton pull --ff-only
git -C modules pull --ff-only
docker compose --profile https up -d --build

docker compose --profile https up -d --build --no-deps web

```

После остановки и до запуска отложи в резервную папку оба каталога: "users/" и "state/"

## fuckup

не приходит код, проверка интерактивно в контейнере
docker compose --profile check-code run --rm --no-deps check-code
