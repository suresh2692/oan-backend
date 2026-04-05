terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.0" }
    random = { source = "hashicorp/random", version = "~> 3.5" }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
}

# ── Data ──────────────────────────────────────────────────────────────────────

data "aws_vpc" "main" {
  id = var.vpc_id
}

data "aws_subnet" "public" {
  id = var.subnet_id
}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023*-x86_64"]
  }
  filter {
    name   = "state"
    values = ["available"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }
}

# ── Secrets (generated once, stored in tfstate) ───────────────────────────────

resource "random_password" "pg" {
  length  = 32
  special = false
}

resource "random_password" "nextauth" {
  length  = 64
  special = false
}

resource "random_password" "salt" {
  length  = 64
  special = false
}

resource "random_password" "clickhouse" {
  length  = 32
  special = false
}

resource "random_password" "minio" {
  length  = 32
  special = false
}

resource "random_password" "lf_public_key" {
  length  = 32
  special = false
}

resource "random_password" "lf_secret_key" {
  length  = 32
  special = false
}

locals {
  tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
    Service     = "langfuse"
  }
  nextauth_url = (
    var.langfuse_hostname != ""
    ? "http://${var.langfuse_hostname}"
    : "http://${aws_eip.langfuse.public_ip}"
  )
}

# ── Security Group ────────────────────────────────────────────────────────────

resource "aws_security_group" "langfuse" {
  name        = "${var.project}-langfuse-sg"
  description = "Langfuse observability server"
  vpc_id      = data.aws_vpc.main.id
  tags        = merge(local.tags, { Name = "${var.project}-langfuse-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

# SSH — restricted to admin CIDR (change from 0.0.0.0/0 in production)
resource "aws_vpc_security_group_ingress_rule" "ssh" {
  security_group_id = aws_security_group.langfuse.id
  description       = "SSH from admin CIDRs only"
  from_port         = 22
  to_port           = 22
  ip_protocol       = "tcp"
  cidr_ipv4         = var.admin_cidr
  tags              = merge(local.tags, { Name = "ssh-admin" })
}

resource "aws_vpc_security_group_ingress_rule" "http" {
  security_group_id = aws_security_group.langfuse.id
  description       = "HTTP"
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
  cidr_ipv4         = "0.0.0.0/0"
  tags              = merge(local.tags, { Name = "http-public" })
}

resource "aws_vpc_security_group_ingress_rule" "https" {
  security_group_id = aws_security_group.langfuse.id
  description       = "HTTPS"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  cidr_ipv4         = "0.0.0.0/0"
  tags              = merge(local.tags, { Name = "https-public" })
}

# Langfuse app port — VPC-internal only (Nginx proxies from 80/443 externally)
resource "aws_vpc_security_group_ingress_rule" "app" {
  security_group_id = aws_security_group.langfuse.id
  description       = "Langfuse app port (VPC internal only)"
  from_port         = 3000
  to_port           = 3000
  ip_protocol       = "tcp"
  cidr_ipv4         = data.aws_vpc.main.cidr_block
  tags              = merge(local.tags, { Name = "langfuse-internal" })
}

resource "aws_vpc_security_group_egress_rule" "all_out" {
  security_group_id = aws_security_group.langfuse.id
  description       = "All outbound"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  tags              = merge(local.tags, { Name = "all-outbound" })
}

# ── IAM: SSM + CloudWatch (no SSH keys needed in prod) ────────────────────────

resource "aws_iam_role" "langfuse" {
  name        = "${var.project}-langfuse-role"
  description = "IAM role for Langfuse EC2"
  tags        = local.tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.langfuse.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "cloudwatch" {
  role       = aws_iam_role.langfuse.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

resource "aws_iam_instance_profile" "langfuse" {
  name = "${var.project}-langfuse-profile"
  role = aws_iam_role.langfuse.name
  tags = local.tags
}

# ── Elastic IP (stable address survives stop/start) ───────────────────────────

resource "aws_eip" "langfuse" {
  domain = "vpc"
  tags   = merge(local.tags, { Name = "${var.project}-langfuse-eip" })
}

resource "aws_eip_association" "langfuse" {
  instance_id   = aws_instance.langfuse.id
  allocation_id = aws_eip.langfuse.id
}

# ── EC2 Instance ──────────────────────────────────────────────────────────────

resource "aws_instance" "langfuse" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  subnet_id              = data.aws_subnet.public.id
  key_name               = var.key_name
  iam_instance_profile   = aws_iam_instance_profile.langfuse.name
  vpc_security_group_ids = [aws_security_group.langfuse.id]

  # IMDSv2 required — prevents SSRF credential theft via metadata endpoint
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 30
    encrypted             = true
    delete_on_termination = true
    tags                  = merge(local.tags, { Name = "${var.project}-langfuse-root" })
  }

  user_data = templatefile("${path.module}/user_data.sh", {
    postgres_password      = random_password.pg.result
    nextauth_secret        = random_password.nextauth.result
    salt                   = random_password.salt.result
    clickhouse_password    = random_password.clickhouse.result
    minio_secret           = random_password.minio.result
    langfuse_public_key    = random_password.lf_public_key.result
    langfuse_secret_key    = random_password.lf_secret_key.result
    langfuse_version       = var.langfuse_version
    langfuse_init_email    = var.langfuse_init_email
    langfuse_init_password = var.langfuse_init_password
    langfuse_hostname      = var.langfuse_hostname
    eip_public_ip          = aws_eip.langfuse.public_ip
  })

  # Don't recreate the instance just because user_data changed after initial apply
  user_data_replace_on_change = false

  tags = merge(local.tags, { Name = "${var.project}-langfuse" })

  lifecycle {
    ignore_changes = [ami] # Don't replace on new AMI releases
  }
}

# ── Outputs ───────────────────────────────────────────────────────────────────

output "public_ip" {
  description = "Elastic IP (stable, survives stop/start)"
  value       = aws_eip.langfuse.public_ip
}

output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.langfuse.id
}

output "langfuse_url" {
  description = "Langfuse web UI"
  value       = local.nextauth_url
}

output "admin_email" {
  description = "Initial admin email"
  value       = var.langfuse_init_email
}

output "ssh_command" {
  description = "SSH into the instance"
  value       = "ssh -i ~/.ssh/oan-infra.pem ec2-user@${aws_eip.langfuse.public_ip}"
}

output "ssm_command" {
  description = "Session Manager access (no SSH key needed)"
  value       = "aws ssm start-session --target ${aws_instance.langfuse.id} --profile ${var.aws_profile} --region ${var.aws_region}"
}

output "watch_setup" {
  description = "Stream the setup log"
  value       = "ssh -i ~/.ssh/oan-infra.pem ec2-user@${aws_eip.langfuse.public_ip} 'tail -f /var/log/user-data.log'"
}

output "langfuse_public_key" {
  description = "Pre-seeded project public key (use in SDK)"
  value       = random_password.lf_public_key.result
  sensitive   = true
}

output "langfuse_secret_key" {
  description = "Pre-seeded project secret key (use in SDK)"
  value       = random_password.lf_secret_key.result
  sensitive   = true
}
