# Brownfield AWS Import Guide (Terraform Search + Import + MCP + Agent Skills)

This directory demonstrates a practical, repeatable workflow for bringing an existing AWS environment (brownfield) under Terraform management.

For this demo, infrastructure is first created with CloudFormation in `cfn-infra/`. After that deployment is complete, treat the environment as unmanaged infrastructure and onboard it into Terraform using:

1. Terraform Search (`list` blocks, `terraform query`)
2. Terraform Import (`import` blocks)
3. Terraform MCP Server
4. Agent Skills

Important: after CloudFormation bootstrap, assume no Terraform files exist for that environment. Use sample prompts in `sample_prompts.md` (or your own prompts) to generate Terraform files with help from MCP Server and Agent Skills.

## Prerequisites

Install and verify all prerequisites before starting the import workflow.

1. Terraform CLI
   - Recommended: Terraform 1.14+
   - Must support Search and Import workflows.

2. Terraform MCP Server
   - Repository: https://github.com/hashicorp/terraform-mcp-server
   - Used for provider/resource/module discovery and up-to-date schema guidance while generating Terraform code.

3. Agent Skills
   - Repository: https://github.com/hashicorp/agent-skills
   - Used to accelerate discovery, mapping, identifier normalization, and drift-stabilization steps.

4. AWS CLI v2 with valid authentication
   - Verify account and credentials before continuing:

```bash
aws sts get-caller-identity
```

5. LLM-enabled editor/client
   - Recommended: VS Code with GitHub Copilot
   - Any equivalent GenAI-capable setup is acceptable.

6. AWS permissions
   - Ensure access to read/import the required resource families: VPC, IAM, EKS, ELBv2, DynamoDB, ECR.
   - Ensure permission for Cloud Control API operations where `awscc` resources are used.

## Demo Bootstrap (CloudFormation First)

Deploy the demo stack first, then treat it as brownfield.

1. Follow `../cfn-infra/README.md` and deploy the CloudFormation stack into your AWS account.
2. Run post-stack setup from that guide (ALB controller + app IRSA + app manifests).
3. Verify the application through the ALB ingress URL.
4. Only after verification, treat the environment as unmanaged brownfield infrastructure.

Mental model: CloudFormation is only the bootstrap mechanism for the demo. Terraform onboarding should be performed as if the environment already existed outside Terraform.

## Application and Infrastructure Context

The demo represents a three-tier system:

1. Networking: VPC, public/private subnets, routing, NAT/internet gateways
2. Compute: EKS cluster + managed node group
3. Routing: ALB ingress path
4. Data: DynamoDB table
5. Registry: ECR repository
6. Identity: IAM roles/policies + OIDC provider for IRSA

Reference files to review before import planning:

1. `../cfn-infra/three-tier-app.yaml`
2. `../cfn-infra/setup-alb-controller.sh`
3. `../cfn-infra/k8s-manifests/app-deployment.yaml`
4. `../cfn-infra/app/app.py`

## Use Sample Prompts to Start Terraform Onboarding

After CloudFormation deployment is verified, start in this directory and use `sample_prompts.md`.

Suggested prompt sequence:

1. Foundation prompts
2. Discovery/mapping prompts
3. Practical sequencing prompt

This is the handoff point where MCP Server + Agent Skills should drive generation/refinement of:

1. `main.tf`
2. `variables.tf`
3. `resources.tf`
4. `imports.tf`
5. `search.tfquery.hcl`

## Brownfield Import Strategy

Use phased execution to reduce risk.

### 1) Scope and Classify

Group resources into domains:

1. Network
2. Security groups/rules
3. IAM/OIDC
4. EKS/compute
5. ALB/load balancing
6. Data/registry

### 2) Provider Split

1. Prefer `awscc` for Cloud Control-backed resource support.
2. Use `aws` where `awscc` support is unavailable or unsuitable.
3. In this demo, `aws_eks_node_group` is handled with `aws`.

### 3) Discovery with Terraform Search

Use `search.tfquery.hcl` with `list` blocks for supported types.

```bash
terraform init
terraform query
```

Optional generated config:

```bash
terraform query -generate-config-out=generated-from-search.tf
```

Note: list support is provider/version dependent. Expect partial discovery and supplement with targeted identity lookups.

### 4) Author Resources and Import Blocks

Maintain explicit Terraform definitions and mappings:

1. `resources.tf` for resource definitions
2. `imports.tf` for import mappings

Prefer committed `import` blocks over one-off CLI imports for repeatability.

### 5) Normalize Import Identifiers (Critical)

Common composite/non-obvious identifier patterns:

1. EIP: `PublicIp|AllocationId`
2. IAM role policy: `PolicyName|RoleName`
3. Subnet route table association: `rtbassoc-*` association ID
4. Some ELBv2 resources: ARN-specific identities
5. Launch template: use `lt-*` ID, not template name

### 6) Validate, Plan, Stabilize Drift, Apply

Drift/noise after import commonly comes from:

1. AWS-managed/computed tags
2. Order-only list/set differences
3. Mixed ownership patterns (for example, inline SG rules plus standalone SG rule resources)

Use targeted lifecycle ignores only where non-functional noise is confirmed.

## Suggested Runbook

Run in this order after bootstrap is complete:

```bash
terraform init
terraform query
terraform fmt -recursive
terraform validate
terraform plan
terraform apply
```

## Review Gates

Before first apply:

1. Validate every import identifier format.
2. Confirm no accidental replacements of critical resources.
3. Review all drift updates and suppress only non-functional noise.
4. Keep a rollback plan for high-impact changes.

## Directory Contents (Sample Generated Outcome)

This directory includes sample generated artifacts you can use as references:

1. `main.tf`
   - Providers (`awscc` + `aws`), Terraform settings, shared locals
2. `variables.tf`
   - Input variables with defaults
3. `resources.tf`
   - Resource definitions across network/security/IAM/EKS/ALB/data/registry
4. `imports.tf`
   - Explicit import blocks with resolved IDs for the demo environment
5. `search.tfquery.hcl`
   - Search list blocks, with unsupported types commented where applicable

## Expected End State

After successful import and stabilization:

1. Existing resources are tracked in Terraform state.
2. Plans are mostly no-op unless intentional changes are made.
3. Ongoing infrastructure lifecycle is managed through Terraform workflows.

## Additional Notes

1. If you run this against a different account/region, regenerate identifiers in `imports.tf`.
2. Keep import mappings and drift controls under version control.
3. Avoid broad ignore rules; prefer minimal, explicit lifecycle controls.
4. Use `sample_prompts.md` as the starting point for consistent LLM-driven execution.
