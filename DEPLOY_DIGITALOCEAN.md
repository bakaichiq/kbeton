# Deploy on DigitalOcean

This repository is best deployed on a single DigitalOcean Droplet with Docker Compose.

Why Droplet instead of App Platform:

- the project runs multiple long-lived containers: `api`, `bot`, `worker`, `beat`
- it also includes stateful services: `postgres`, `redis`, `minio`
- the Telegram bot uses long polling, so no public webhook endpoint is required

## 1. Recommended server shape

Minimum for a test/staging server:

- `2 vCPU`
- `4 GB RAM`
- `80 GB SSD`

Recommended for production:

- `2-4 vCPU`
- `4-8 GB RAM`
- backups enabled

Inference: the compose stack in this repo runs 6 persistent services plus a migration job, so a very small Droplet is likely to become memory-constrained.

## 2. Create the Droplet

Create an Ubuntu 24.04 Droplet in DigitalOcean and add your SSH key during creation.

Recommended options:

- region close to your users
- hostname: `kbeton-prod`
- automatic backups: enabled
- monitoring: enabled

If you plan to expose the API on a domain, create a DNS `A` record like `api.example.com -> <droplet_ip>`.

## 3. Configure DigitalOcean firewall

This repository's base compose file publishes several ports. For production, use both:

- a DigitalOcean Cloud Firewall
- the production override file in this repo: `docker-compose.prod.yml`

Allow inbound only:

- `22/tcp` from your office/home IPs
- `80/tcp` from anywhere
- `443/tcp` from anywhere

Do not open:

- `5432`
- `6379`
- `8000`
- `9000`
- `9001`

## 4. Prepare the server

SSH to the server:

```bash
ssh root@YOUR_DROPLET_IP
```

Create a deploy user:

```bash
adduser deploy
usermod -aG sudo deploy
mkdir -p /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
```

Install Docker Engine and Docker Compose plugin using the official Docker instructions for Ubuntu.

After Docker is installed, add the deploy user to the `docker` group:

```bash
sudo usermod -aG docker deploy
```

Then reconnect as `deploy` so the new group membership is applied.

After installation, verify:

```bash
docker --version
docker compose version
```

Install git and nginx:

```bash
sudo apt update
sudo apt install -y git nginx
```

## 5. Clone the project

As user `deploy`:

```bash
sudo su - deploy
mkdir -p /opt
cd /opt
git clone YOUR_GITHUB_REPO_URL kbeton_bot_erp_full
cd /opt/kbeton_bot_erp_full
```

## 6. Create production environment

Copy the example env:

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```dotenv
ENV=prod
TZ=Asia/Bishkek
LOG_LEVEL=INFO

POSTGRES_DB=kbeton
POSTGRES_USER=kbeton
POSTGRES_PASSWORD=CHANGE_ME_TO_A_LONG_RANDOM_PASSWORD
DATABASE_URL=postgresql+psycopg2://kbeton:CHANGE_ME_TO_A_LONG_RANDOM_PASSWORD@postgres:5432/kbeton

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
BOT_FSM_STORAGE=redis
BOT_FSM_REDIS_URL=redis://redis:6379/3

TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
TELEGRAM_DEFAULT_CHAT_ID=

API_AUTH_ENABLED=true
API_TOKEN=CHANGE_ME_TO_A_LONG_RANDOM_API_TOKEN

S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY_ID=CHANGE_ME_MINIO_ACCESS_KEY
S3_SECRET_ACCESS_KEY=CHANGE_ME_MINIO_SECRET_KEY
S3_BUCKET=kbeton
S3_REGION=us-east-1
```

Notes:

- `DATABASE_URL` must match `POSTGRES_PASSWORD`
- the bot will not start without `TELEGRAM_BOT_TOKEN`
- this repo currently assumes local Redis DB indexes `0/1/2/3`, so the simplest production deployment is to keep the bundled Redis container
- this repo also initializes MinIO automatically, so the simplest production deployment is to keep the bundled MinIO container

## 7. Start the stack

Build the base image and start production compose:

```bash
docker build -f docker/Dockerfile.base -t kbeton-base:latest .
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Check status:

```bash
docker compose ps
docker compose logs -f migrate
docker compose logs -f api
docker compose logs -f bot
docker compose logs -f worker
docker compose logs -f beat
```

Important:

- `migrate` should exit successfully
- `api`, `bot`, `worker`, `beat`, `postgres`, `redis`, `minio` should remain `Up`

## 8. Verify locally on the server

Because `docker-compose.prod.yml` binds the API only to localhost, verify from the server:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"ok":true}
```

MinIO console is also local-only:

- API: `http://127.0.0.1:9000`
- console: `http://127.0.0.1:9001`

If needed, reach it through SSH tunnel from your laptop:

```bash
ssh -L 9001:127.0.0.1:9001 deploy@YOUR_DROPLET_IP
```

## 9. Put Nginx in front of the API

Create `/etc/nginx/sites-available/kbeton-api`:

```nginx
server {
    listen 80;
    server_name api.example.com;

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable it:

```bash
sudo ln -s /etc/nginx/sites-available/kbeton-api /etc/nginx/sites-enabled/kbeton-api
sudo nginx -t
sudo systemctl reload nginx
```

At this point:

- `http://api.example.com/health` should work
- protected endpoints still require `Authorization: Bearer <API_TOKEN>` or `X-API-Key`

## 10. Enable HTTPS

Install Certbot using the official Certbot instructions for Ubuntu + Nginx, then request a certificate for your API domain.

Typical flow:

```bash
sudo certbot --nginx -d api.example.com
```

Then verify:

```bash
curl https://api.example.com/health
```

## 11. Create the first admin user

Get your Telegram numeric ID from the bot via `/id`, then run:

```bash
docker compose run --rm api python scripts/create_user.py --tg-id YOUR_TG_ID --name "Your Name" --role Admin
```

Optional demo data:

```bash
docker compose run --rm api python scripts/seed_demo.py
```

## 12. Daily operations

Useful commands:

```bash
docker compose logs -f api
docker compose logs -f bot
docker compose logs -f worker
docker compose exec postgres psql -U kbeton -d kbeton
docker compose restart api bot worker beat
```

Upgrade to a new version:

```bash
cd /opt/kbeton_bot_erp_full
git pull origin main
docker build -f docker/Dockerfile.base -t kbeton-base:latest .
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## 13. Optional GitHub autodeploy

This repository already contains `.github/workflows/deploy-on-push.yml`.

To use it, add these GitHub secrets:

- `DEPLOY_HOST`
- `DEPLOY_USER`
- `DEPLOY_PATH`
- `DEPLOY_SSH_KEY`

Before enabling the workflow, update it so the remote command uses the production override:

```bash
docker build -f docker/Dockerfile.base -t kbeton-base:latest .
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## 14. Backups and production hardening

Minimum:

- enable Droplet backups
- create regular database dumps
- keep a copy of `.env` in a password manager or secret store
- monitor disk space with `df -h`
- monitor container restarts with `docker compose ps`

PostgreSQL backup example:

```bash
mkdir -p /opt/backups
docker compose exec -T postgres pg_dump -U kbeton -d kbeton > /opt/backups/kbeton-$(date +%F).sql
```

Recommended next improvements:

- move Postgres to DigitalOcean Managed PostgreSQL
- move object storage from local MinIO to DigitalOcean Spaces
- add a second server or managed services before critical production usage

## 15. Files in this repo relevant to deployment

- `docker-compose.yml`
- `docker-compose.prod.yml`
- `.env.example`
- `docker/Dockerfile.base`
- `docker/Dockerfile.api`
- `docker/Dockerfile.bot`
- `docker/Dockerfile.worker`
- `docker/Dockerfile.beat`
- `.github/workflows/deploy-on-push.yml`
