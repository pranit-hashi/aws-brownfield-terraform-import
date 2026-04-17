#!/bin/bash
set -e

# Configuration
CLUSTER_NAME="demo-eks-cluster"
AWS_REGION="${AWS_REGION:-$(aws configure get region 2>/dev/null || true)}"
STACK_NAME="${STACK_NAME:-three-tier-app}"
APP_NAMESPACE="user-app"
APP_SERVICE_ACCOUNT="user-app-sa"

if [ -z "$AWS_REGION" ]; then
  echo "Error: Region is not set. Export AWS_REGION or configure a default AWS CLI region."
  exit 1
fi

get_stack_output() {
  local output_key="$1"
  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='${output_key}'].OutputValue" \
    --output text
}

echo "================================================"
echo "AWS Load Balancer Controller Setup Script"
echo "================================================"
echo "Cluster: $CLUSTER_NAME"
echo "Region: $AWS_REGION"
echo "Stack: $STACK_NAME"
echo "================================================"

# Step 1: Update kubeconfig
echo ""
echo "Step 1: Updating kubeconfig..."
aws eks update-kubeconfig --name $CLUSTER_NAME --region $AWS_REGION

# Step 2: Read role ARNs from CloudFormation outputs
echo ""
echo "Step 2: Reading IAM role ARNs from stack outputs..."
CONTROLLER_ROLE_ARN=$(get_stack_output "LoadBalancerControllerRoleArn")
APP_ROLE_ARN=$(get_stack_output "UserAppDynamoDBRoleArn")

if [ -z "$CONTROLLER_ROLE_ARN" ] || [ "$CONTROLLER_ROLE_ARN" = "None" ]; then
  echo "Error: LoadBalancerControllerRoleArn output not found in stack '$STACK_NAME'."
  echo "Update/redeploy CloudFormation stack first."
  exit 1
fi

if [ -z "$APP_ROLE_ARN" ] || [ "$APP_ROLE_ARN" = "None" ]; then
  echo "Error: UserAppDynamoDBRoleArn output not found in stack '$STACK_NAME'."
  echo "Update/redeploy CloudFormation stack first."
  exit 1
fi

echo "Controller role ARN: $CONTROLLER_ROLE_ARN"
echo "App role ARN: $APP_ROLE_ARN"

# Step 3: Prepare namespace for controller
echo ""
echo "Step 3: Ensuring controller namespace exists..."
kubectl create namespace kube-system 2>/dev/null || true

# Step 4: Install AWS Load Balancer Controller using Helm
echo ""
echo "Step 4: Installing AWS Load Balancer Controller via Helm..."

# Add EKS chart repo
helm repo add eks https://aws.github.io/eks-charts
helm repo update

# Install the controller
helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=$CLUSTER_NAME \
  --set serviceAccount.create=true \
  --set serviceAccount.name=aws-load-balancer-controller \
  --set-string serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn=$CONTROLLER_ROLE_ARN \
  --set region=$AWS_REGION \
  --set vpcId=$(aws eks describe-cluster --name $CLUSTER_NAME --region $AWS_REGION --query "cluster.resourcesVpcConfig.vpcId" --output text) \
  --wait

# Step 5: Verify installation
echo ""
echo "Step 5: Verifying installation..."
sleep 10
kubectl get deployment -n kube-system aws-load-balancer-controller

# Step 6: Reminder for application service account annotation via manifest
echo ""
echo "Step 6: Set app service account role ARN in k8s-manifests/app-deployment.yaml before apply:"
echo "        eks.amazonaws.com/role-arn: $APP_ROLE_ARN"

echo ""
echo "================================================"
echo "✅ Controller install completed successfully!"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Update your Kubernetes manifests if needed"
echo "2. Deploy your application: kubectl apply -f k8s-manifests/app-deployment.yaml"
echo "3. Check ingress: kubectl get ingress -n user-app"
echo ""
