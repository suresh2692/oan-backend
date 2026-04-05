variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ap-south-1"
}

variable "aws_profile" {
  description = "AWS CLI profile to use"
  type        = string
  default     = "suresh-protean"
}

variable "vpc_id" {
  description = "Existing VPC ID"
  type        = string
  default     = "vpc-098db793507cb54ea"
}

variable "subnet_id" {
  description = "Public subnet ID within the VPC"
  type        = string
  default     = "subnet-044c70eb69042c9b6"
}

variable "key_name" {
  description = "EC2 key pair name for SSH access"
  type        = string
  default     = "oan-infra"
}

variable "instance_type" {
  description = "EC2 instance type (t3.large minimum for Langfuse v3)"
  type        = string
  default     = "t3.large"
}

variable "root_volume_size" {
  description = "Root EBS volume size in GB"
  type        = number
  default     = 30
}

variable "admin_cidr_blocks" {
  description = "CIDR blocks allowed to SSH (port 22). Restrict to your IP in production."
  type        = list(string)
  default     = ["0.0.0.0/0"] # Override in tfvars with your IP: e.g. ["1.2.3.4/32"]
}

variable "langfuse_hostname" {
  description = "Public hostname or IP for Langfuse (used for NEXTAUTH_URL). Leave empty to use EC2 public IP."
  type        = string
  default     = ""
}

variable "langfuse_init_email" {
  description = "Initial admin user email"
  type        = string
  default     = "admin@admin.com"
}

variable "langfuse_init_password" {
  description = "Initial admin user password (min 8 chars)"
  type        = string
  default     = "admin123"
  sensitive   = true
}

variable "langfuse_version" {
  description = "Langfuse Docker image tag"
  type        = string
  default     = "3"
}

variable "environment" {
  description = "Environment tag (e.g. dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "project" {
  description = "Project name for tagging"
  type        = string
  default     = "oan"
}
