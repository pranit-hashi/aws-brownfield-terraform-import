# Three-Tier Application with ALB, EKS 1.35, and DynamoDB

This project contains a complete AWS CloudFormation template for deploying a three-tier application architecture.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                  Internet                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Application Load Balancer                             │
│                         (Public Subnets - AZ1/AZ2)                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Amazon EKS Cluster                                │
│                          (Kubernetes v1.35)                                  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         EKS Node Group                                 │  │
│  │                    (Private Subnets - AZ1/AZ2)                        │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐       │  │
│  │  │   User App Pod  │  │   User App Pod  │  │   User App Pod  │       │  │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Amazon DynamoDB                                   │
│                           (User Data Table)                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. CloudFormation Template (`three-tier-app.yaml`)
- **VPC**: 10.0.0.0/16 with 2 public and 2 private subnets across 2 AZs
- **Internet Gateway**: For public internet access
- **NAT Gateway**: For private subnet internet access
- **Security Groups**: For ALB, EKS cluster, and worker nodes
- **EKS Cluster**: Kubernetes 1.35 with managed node group
- **EKS Node Launch Template**: Enables EC2 metadata access with hop limit 2 for container workloads
- **IAM + OIDC for IRSA**: CloudFormation creates OIDC provider and IAM roles for ALB controller and app service account
- **ECR Repository**: CloudFormation creates the `user-data-app` repository for container images
- **Application Load Balancer**: Internet-facing ALB with target group
- **DynamoDB Table**: User data table with on-demand capacity

### 2. Kubernetes Manifests (`k8s-manifests/`)
- Namespace, ConfigMap, Deployment, Service
- Ingress for ALB integration
- HorizontalPodAutoscaler for auto-scaling

### 3. Sample Application (`app/`)
- Python Flask application
- Takes user input (name, email, message)
- Stores data in DynamoDB
- REST API endpoints
- Health check endpoints

## Prerequisites

- AWS CLI configured with appropriate permissions
- kubectl installed
- Docker (for building the application image)

Set environment variables once and reuse them in commands:

```bash
export AWS_REGION=<YOUR_AWS_REGION>
export ACCOUNT_ID=<YOUR_ACCOUNT_ID>
```

## Deployment Steps

### Step 1: Deploy CloudFormation Stack

```bash
aws cloudformation create-stack \
  --stack-name three-tier-app \
  --template-body file://cfn-infra/three-tier-app.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --region $AWS_REGION \
  --parameters \
    ParameterKey=EnvironmentName,ParameterValue=demo \
    ParameterKey=EKSClusterVersion,ParameterValue=1.35
```

### Step 2: Build and Push Docker Image While the Stack Provisions

The full CloudFormation stack usually takes around 15 minutes to finish, but the ECR repository is created almost immediately. As soon as the stack creation command is submitted, you can build and push the application image in parallel:

```bash
cd app

# Get ECR login
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Build and push
docker buildx build --platform linux/amd64,linux/arm64 \
  -t $ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/user-data-app:latest \
  --push .
```

### Step 3: Wait for Stack Creation

```bash
aws cloudformation wait stack-create-complete --stack-name three-tier-app --region $AWS_REGION
```

### Step 4: Run Cluster-Side Controller Setup

```bash
cd ../cfn-infra/

# CloudFormation creates IAM/OIDC resources for IRSA.
# This script reads role ARNs from stack outputs and performs cluster-side setup:
# 1) Install/upgrade AWS Load Balancer Controller via Helm
# 2) Configure controller service account annotation through Helm values
# Optional: set STACK_NAME if your stack is not named three-tier-app
# export STACK_NAME=<your_stack_name>
./setup-alb-controller.sh
```

### Step 5: Update Kubernetes Manifest and Deploy

Update both of the following in `k8s-manifests/app-deployment.yaml` using your own environment values:
- `image` to `<YOUR_ACCOUNT_ID>.dkr.ecr.<YOUR_AWS_REGION>.amazonaws.com/user-data-app:latest`

You can fetch the ECR URI with:
```bash
aws cloudformation describe-stacks \
  --stack-name three-tier-app \
  --region $AWS_REGION \
  --query "Stacks[0].Outputs[?OutputKey=='ECRRepositoryUri'].OutputValue" \
  --output text
```
- `AWS_REGION` in the `app-config` ConfigMap to the same `<YOUR_AWS_REGION>` value
- `eks.amazonaws.com/role-arn` under `user-app-sa` to your `UserAppDynamoDBRoleArn` stack output

You can use this one-liner after the stack is complete to fetch the role ARN and update the manifest in place:

```bash
APP_ROLE_ARN=$(aws cloudformation describe-stacks --stack-name three-tier-app --region $AWS_REGION --query "Stacks[0].Outputs[?OutputKey=='UserAppDynamoDBRoleArn'].OutputValue" --output text) && sed -i.bak "s|<IAM_ROLE_ARN>|$APP_ROLE_ARN|g" k8s-manifests/app-deployment.yaml
```

If you exported variables in prerequisites, this should match:
- Account ID: `$ACCOUNT_ID`
- AWS Region: `$AWS_REGION`

Then apply:

```bash
kubectl apply -f k8s-manifests/app-deployment.yaml
```

### Step 6: Verify Deployment

```bash
# Check pods
kubectl get pods -n user-app

# Get ALB URL
kubectl get ingress -n user-app
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Web form for data entry |
| POST | `/submit` | Submit form data |
| POST | `/api/submit` | API endpoint for JSON data |
| GET | `/api/data` | Get all submissions |
| GET | `/api/data/<user_id>` | Get specific submission |
| GET | `/health` | Health check |
| GET | `/ready` | Readiness check |

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| EnvironmentName | demo | Environment name prefix |
| VpcCIDR | 10.0.0.0/16 | VPC CIDR block |
| EKSClusterVersion | 1.35 | EKS Kubernetes version |
| NodeInstanceType | t3.medium | EC2 instance type for nodes |
| NodeGroupDesiredSize | 2 | Desired number of nodes |

## Outputs

After deployment, the stack exports:
- VPC ID
- Subnet IDs
- EKS Cluster Name and Endpoint
- ALB DNS Name
- DynamoDB Table Name and ARN
- ECR Repository URI

## Cleanup

```bash
# Delete Kubernetes resources
kubectl delete -f k8s-manifests/app-deployment.yaml

# Delete ECR repository and all images before deleting the stack
# CloudFormation cannot delete a non-empty repository
aws ecr delete-repository --repository-name user-data-app --region $AWS_REGION --force

# Delete CloudFormation stack
aws cloudformation delete-stack --stack-name three-tier-app
```

## Security Considerations

- EKS nodes are deployed in private subnets
- DynamoDB table has encryption at rest enabled
- Point-in-time recovery enabled for DynamoDB
- Security groups follow least privilege principle
- Use IRSA (IAM Roles for Service Accounts) for pod-level permissions
