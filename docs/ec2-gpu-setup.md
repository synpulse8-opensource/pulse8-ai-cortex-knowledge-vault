# EC2 GPU Setup for QMD

This guide walks through provisioning and configuring an AWS EC2 instance so that the QMD container uses NVIDIA GPU acceleration for embedding, reranking, and query expansion.

## 1. Instance Selection

| Spec | Recommendation |
|---|---|
| Instance type | `g4dn.xlarge` |
| GPU | 1× NVIDIA T4 (16 GB VRAM) |
| vCPUs | 4 |
| RAM | 16 GB |
| Storage | 125 GB NVMe SSD (included) |
| Pricing | ~$0.53/hr on-demand, ~$0.16–0.20/hr spot |

The T4's 16 GB VRAM is more than enough for QMD's three models (~2 GB total). Use spot instances for non-critical workloads to save ~65%.

### Alternative instances

| Instance | GPU | VRAM | Cost/hr |
|---|---|---|---|
| `g6.xlarge` | 1× NVIDIA L4 | 24 GB | ~$0.98 |
| `g5.xlarge` | 1× NVIDIA A10G | 24 GB | ~$1.01 |

Only needed if `g4dn` is unavailable in your region.

## 2. AMI and OS

Use one of the following:

- **Amazon Linux 2023 with NVIDIA drivers** (recommended)
  - AMI: Search for `Deep Learning AMI GPU` in the EC2 console — comes with NVIDIA drivers pre-installed.
- **Ubuntu 22.04/24.04** — requires manual driver installation (see step 3).

If you use a Deep Learning AMI, skip to step 4.

## 3. Install NVIDIA Drivers (Ubuntu only)

```bash
sudo apt-get update
sudo apt-get install -y linux-headers-$(uname -r)

# Add NVIDIA driver repo
sudo apt-get install -y nvidia-driver-550
sudo reboot
```

After reboot, verify:

```bash
nvidia-smi
```

You should see the T4 GPU listed with driver version and VRAM.

## 4. Install Docker and Docker Compose

```bash
# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker --version
docker compose version
```

## 5. Install NVIDIA Container Toolkit

This allows Docker containers to access the GPU.

```bash
# Add NVIDIA container toolkit repo
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Configure Docker runtime
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Verify GPU is visible inside containers:

```bash
docker run --rm --gpus all nvidia/cuda:12.8.1-runtime-ubuntu24.04 nvidia-smi
```

You should see the same T4 GPU output as the host.

## 6. Deploy Cortex + QMD with GPU

```bash
# Clone the repo
git clone git@github.com:synpulse-group/pulse8-ai-cortex-knowledge-vault.git
cd pulse8-ai-cortex-knowledge-vault

# Configure environment
cp .env.example .env
# Edit .env — set LLM_API_KEY at minimum

# Launch with GPU overlay
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
```

The GPU overlay (`docker-compose.gpu.yml`) does two things:
- Builds QMD from `Dockerfile.gpu` (CUDA 12.8 runtime + Node.js 22)
- Reserves the NVIDIA GPU device for the QMD container

## 7. Verify GPU Acceleration

Check QMD logs for GPU status:

```bash
docker compose logs qmd
```

You should see embed completing without the `no GPU acceleration` warning. You can also exec into the container:

```bash
docker compose exec qmd nvidia-smi
```

## 8. Scaling Multiple QMD Instances (Optional)

A single `g4dn.xlarge` can run 2–3 QMD instances sharing the GPU. Each instance uses ~2 GB VRAM.

Create a `docker-compose.scale.yml`:

```yaml
services:
  qmd-1:
    extends:
      file: docker-compose.yml
      service: qmd
    container_name: qmd-1
    ports:
      - "3100:3100"
    volumes:
      - ${VAULT_DIR:-./example_vault}:/vault:ro
      - qmd-cache-1:/home/qmd/.cache/qmd

  qmd-2:
    extends:
      file: docker-compose.yml
      service: qmd
    container_name: qmd-2
    ports:
      - "3101:3100"
    volumes:
      - ${VAULT_DIR:-./example_vault}:/vault:ro
      - qmd-cache-2:/home/qmd/.cache/qmd

volumes:
  qmd-cache-1:
  qmd-cache-2:
```

Put a load balancer (e.g. NGINX, ALB) in front and point Cortex to it:

```bash
CORTEX_QMD_URL=http://qmd-lb:3100
```

## 9. Cost Estimates (Monthly, 24/7)

| Setup | Instance | Pricing | Monthly |
|---|---|---|---|
| Single QMD + Cortex | g4dn.xlarge | On-demand | ~$379 |
| Single QMD + Cortex | g4dn.xlarge | Spot | ~$115–144 |
| Business hours only (8h × 22d) | g4dn.xlarge | Spot | ~$28–35 |

## 10. Security Checklist

- [ ] Place EC2 in a private subnet (no public IP for QMD)
- [ ] Use security groups to restrict port 3100 to Cortex only
- [ ] Enable `AUTH_METHOD=apikey` or `AUTH_METHOD=oidc` on Cortex
- [ ] Use encrypted EBS volumes for the vault data
- [ ] Enable CloudWatch logs for container output
- [ ] Use IAM instance profile (no access keys on the instance)
