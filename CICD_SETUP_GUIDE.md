# 🚀 ResearchMate – AWS CI/CD & Deployment Guide

This document provides the complete, production-ready setup guide to configure continuous integration, automated testing, and automated deployment of the **ResearchMate** FastAPI platform onto **Amazon Web Services (AWS)** using **GitHub Actions**, **Amazon ECR**, **Amazon RDS (PostgreSQL + pgvector)**, **Amazon ElastiCache (Redis)**, and **Amazon EC2/ALB**.

---

## 📑 Table of Contents
1. [Architecture Overview](#1-architecture-overview)
2. [Prerequisites](#2-prerequisites)
3. [Step 1: Provision Infrastructure with Terraform](#3-step-1-provision-infrastructure-with-terraform)
4. [Step 2: Configure AWS Secrets Manager](#4-step-2-configure-aws-secrets-manager)
5. [Step 3: Configure GitHub Repository Secrets](#5-step-3-configure-github-repository-secrets)
6. [Step 4: Continuous Integration (CI Pipeline)](#6-step-4-continuous-integration-ci-pipeline)
7. [Step 5: Continuous Deployment (CD Pipeline)](#7-step-5-continuous-deployment-cd-pipeline)
8. [Step 6: Database & pgvector Verification](#8-step-6-database--pgvector-verification)
9. [Operational Commands & Troubleshooting](#9-operational-commands--troubleshooting)

---

## 1. Architecture Overview

```
                        ┌───────────────────────────────┐
                        │      Developer / Git Push     │
                        └──────────────┬────────────────┘
                                       │
                        ┌──────────────▼────────────────┐
                        │      GitHub Actions (CI)      │
                        │   - Ruff Linting              │
                        │   - 108 Pytest Unit Tests     │
                        │   - Docker Image Smoke Test   │
                        └──────────────┬────────────────┘
                                       │ (On merge to main)
                        ┌──────────────▼────────────────┐
                        │      GitHub Actions (CD)      │
                        │   - Build Docker Image        │
                        │   - Push to Amazon ECR        │
                        │   - SSH Deploy to EC2         │
                        └──────────────┬────────────────┘
                                       │
═══════════════════════════════════════╪═══════════════════════════════════════
                              AWS CLOUD (ap-south-1)
                                       │
                        ┌──────────────▼────────────────┐
                        │   Route 53 / Internet Users   │
                        └──────────────┬────────────────┘
                                       │
                        ┌──────────────▼────────────────┐
                        │  Application Load Balancer    │
                        │  (Port 80 / 443 HTTPS + ACM)  │
                        └──────────────┬────────────────┘
                                       │
                                ┌──────┴──────┐
                                │ EC2 (Docker)│
                                │ ┌─────────┐ │
                                │ │  Nginx  │ │ (Port 80)
                                │ └────┬────┘ │
                                │      │      │
                                │ ┌────▼────┐ │
                                │ │ FastAPI │ │ (Port 5000, Uvicorn)
                                │ └────┬────┘ │
                                └──────┼──────┘
                                       │
              ┌────────────────────────┴────────────────────────┐
              │                                                 │
    ┌─────────▼─────────┐                             ┌─────────▼─────────┐
    │  Amazon RDS (Postgres 15)                       │ Amazon ElastiCache│
    │  + pgvector extension                           │ (Redis 7 Cluster) │
    └───────────────────┘                             └───────────────────┘
              ▲
              │
    ┌─────────┴─────────┐
    │AWS Secrets Manager│ (All sensitive environment variables)
    └───────────────────┘
```

---

## 2. Prerequisites

1. **AWS Account**: An active AWS account with administrative access.
2. **AWS CLI v2**: Installed and configured locally (`aws configure`).
3. **Terraform**: CLI version `>= 1.6.0` installed (`terraform -version`).
4. **SSH Key Pair**: Created in AWS EC2 Console (e.g., `researchmate-key.pem`).
5. **S3 Bucket for Terraform State**: Create an S3 bucket in your target region:
   ```bash
   aws s3 mb s3://researchmate-tfstate --region ap-south-1
   ```

---

## 3. Step 1: Provision Infrastructure with Terraform

All Infrastructure-as-Code files are located in `infra/terraform/`.

### 3.1 Create your `terraform.tfvars`
Navigate to `infra/terraform/` and create `terraform.tfvars`:

```hcl
aws_region         = "ap-south-1"
project_name       = "researchmate"
environment        = "prod"
ec2_instance_type  = "t3.medium"
ec2_key_pair_name  = "researchmate-key"  # Name of your AWS EC2 key pair

# Database Credentials
db_name            = "researchmate"
db_username        = "rmadmin"
db_password        = "ReplaceWithStrongPassword123!" # Change this!
```

### 3.2 Initialize and Apply Terraform
```bash
cd infra/terraform

# Initialize providers and remote S3 state
terraform init

# Review execution plan
terraform plan

# Apply and provision resources
terraform apply -auto-approve
```

### 3.3 Note Down Outputs
Upon completion, Terraform will output:
- `alb_dns_name`: Public URL of your application load balancer.
- `ec2_public_ip`: Public IP address of the EC2 instance.
- `ecr_repository_url`: ECR repository URI (e.g. `123456789012.dkr.ecr.ap-south-1.amazonaws.com/researchmate-api`).
- `rds_endpoint`: PostgreSQL endpoint host and port.
- `redis_endpoint`: Redis endpoint host.

---

## 4. Step 2: Configure AWS Secrets Manager

Terraform creates the secret container `researchmate/prod`. Update its actual values with your live API keys:

```bash
aws secretsmanager put-secret-value \
  --secret-id "researchmate/prod" \
  --region ap-south-1 \
  --secret-string '{
    "SECRET_KEY": "your-super-secret-flask-and-app-key",
    "JWT_SECRET_KEY": "your-super-secret-jwt-signing-key",
    "DATABASE_URL": "postgresql://rmadmin:ReplaceWithStrongPassword123!@<RDS_ENDPOINT>:5432/researchmate",
    "REDIS_URL": "redis://<REDIS_ENDPOINT>:6379/0",
    "GEMINI_API_KEY": "your-actual-google-gemini-api-key",
    "GEMINI_MODEL": "gemini-2.5-flash",
    "GOOGLE_CLIENT_ID": "your-google-oauth-client-id.apps.googleusercontent.com",
    "GOOGLE_CLIENT_SECRET": "your-google-oauth-client-secret",
    "FRONTEND_URL": "http://<ALB_DNS_NAME>",
    "UVICORN_WORKERS": "2"
  }'
```

> **Note**: When the container boots on EC2, `scripts/entrypoint.sh` automatically reads this secret, sets the environment variables, runs Alembic migrations, and launches Uvicorn.

---

## 5. Step 3: Configure GitHub Repository Secrets

In your GitHub repository, go to **Settings > Secrets and variables > Actions > New repository secret** and add the following:

| Secret Name | Description / Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | AWS IAM Access Key with ECR push permissions |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM Secret Access Key |
| `EC2_HOST` | Value from `terraform output ec2_public_ip` |
| `EC2_SSH_KEY` | Contents of your private SSH key file (`.pem`) |
| `CODECOV_TOKEN` | *(Optional)* Token for uploading test coverage |

---

## 6. Step 4: Continuous Integration (CI Pipeline)

The CI pipeline runs on every push or pull request to `main` and `develop` via `.github/workflows/ci.yml`.

### What CI Executes:
1. **Linting (`ruff`)**: Checks code style and syntax across `app/` and `tests/`.
2. **Automated Testing (`pytest`)**: Runs all **108 test cases** using an in-memory SQLite engine and mocked LLM/RAG layers via `requirements-ci.txt`.
3. **Coverage Report**: Generates `coverage.xml` and prints a missing-lines terminal breakdown.
4. **Docker Smoke Build**: Verifies that the production `Dockerfile` builds without errors.

To run the CI test suite locally before pushing:
```bash
pytest tests/ -v
```

---

## 7. Step 5: Continuous Deployment (CD Pipeline)

The CD pipeline runs automatically whenever code is merged into `main` via `.github/workflows/deploy.yml`.

### Deployment Steps:
1. **ECR Login**: Authenticates GitHub Actions with your private Amazon ECR registry.
2. **Container Build & Push**: Builds the image and tags it with both the git commit SHA and `latest`.
3. **Config Synchronization**: Copies `docker-compose.prod.yml` and `nginx/nginx.conf` to `/opt/researchmate` on the EC2 instance via SCP.
4. **Zero-Downtime Rolling Update**:
   - Pulls the latest container image on EC2.
   - Runs `docker compose -f docker-compose.prod.yml up -d`.
   - `scripts/entrypoint.sh` runs `alembic upgrade head` to apply any new database schema migrations.
   - Launches Uvicorn workers behind Nginx.
5. **Healthcheck**: Verifies that `/health` returns `200 OK`.

---

## 8. Step 6: Database & pgvector Verification

To verify that PostgreSQL and the `pgvector` extension are functioning correctly:

1. **SSH into the EC2 Instance**:
   ```bash
   ssh -i researchmate-key.pem ubuntu@<EC2_PUBLIC_IP>
   ```

2. **Check Container Status**:
   ```bash
   docker ps
   ```

3. **Verify Database Migrations & Vector Extension**:
   ```bash
   docker exec -it researchmate_api alembic current
   ```

4. **Test Vector Extension Directly in PostgreSQL**:
   ```bash
   # Connect to RDS from inside the container
   docker exec -it researchmate_api python3 -c "
   from app.database import engine
   from sqlalchemy import text
   with engine.connect() as conn:
       res = conn.execute(text('SELECT * FROM pg_extension WHERE extname = \'vector\';')).fetchall()
       print('Vector extension enabled:', bool(res))
   "
   ```

---

## 9. Operational Commands & Troubleshooting

### Viewing Real-Time Logs
```bash
# View FastAPI application logs
docker logs -f researchmate_api

# View Nginx access/error logs
docker logs -f researchmate_nginx
```

### Restarting the Application
```bash
cd /opt/researchmate
docker compose -f docker-compose.prod.yml restart api
```

### Applying Manual Database Migrations
```bash
docker exec -it researchmate_api alembic upgrade head
```

### Creating a New Migration
When modifying ORM models in `app/models/models.py`:
```bash
# Create an auto-generated migration file
alembic revision --autogenerate -m "describe_changes"

# Commit the new migration file in migrations/versions/ and push to GitHub
```

### Destroying Cloud Resources (To Avoid Incurring Costs)
```bash
cd infra/terraform
terraform destroy -auto-approve
```
