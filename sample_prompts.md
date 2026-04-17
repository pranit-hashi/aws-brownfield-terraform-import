# Helper Prompts for Brownfield AWS Import to Terraform

> Note: These are sample prompts intended for reference only. You should tune and adapt them to your own environment, constraints, and delivery requirements.

> Important: LLM outputs vary by model, model version, temperature/settings, and runtime context. Two runs may not produce identical results, even with the same prompt. Always review, test, and validate generated output before using it in production.

Use these prompts when working with a GenAI model to follow the brownfield import guide in this directory. These are intentionally generic and reusable across AWS environments.

## How to use this file

1. Start with the Foundation prompts.
2. Move to Discovery and Mapping prompts.
3. Use the Practical sequencing prompt to run the workflow end-to-end.
4. Prefer iterative runs instead of one giant prompt.

Note: You may be able to generate successful Terraform import outputs using only the master prompt, depending on the model and context provided. The remaining prompts in this file are optional references to improve structure, troubleshooting, and repeatability; they are not mandatory to use all at once.

## Prompt variables

Replace these placeholders in prompts as needed:

- `<REGION>`
- `<WORKDIR>`
- `<TEMPLATE_PATH>`
- `<K8S_MANIFEST_PATH>`
- `<APP_PATH>`
- `<OUTPUT_DIR>`

Suggested defaults for this repo:

- `<WORKDIR>`: `import-demo-skills`
- `<TEMPLATE_PATH>`: `cfn-infra/three-tier-app.yaml`
- `<K8S_MANIFEST_PATH>`: `cfn-infra/k8s-manifests/app-deployment.yaml`
- `<APP_PATH>`: `cfn-infra/app`
- `<OUTPUT_DIR>`: `tf-import-demo`

---

## A) Foundation prompts

### 1) Master prompt (reference)

"Review the provided AWS CloudFormation template and identify all resources it creates. Using Terraform’s import and search capabilities, generate the required Terraform configuration and import each of those existing resources from the `<REGION>` AWS region into Terraform. Store all Terraform files inside a directory named `<OUTPUT_DIR>`, ensuring resource names, types, and dependencies are correctly mapped."

### 2) Architecture comprehension prompt

"Review `<TEMPLATE_PATH>`, `<K8S_MANIFEST_PATH>`, and `<APP_PATH>`. Summarize the application architecture, networking model, compute platform, ingress path, data stores, IAM/IRSA design, and runtime dependencies. Then list which resources are infrastructure-only versus Kubernetes runtime artifacts."

### 3) Brownfield planning prompt

"Given this existing AWS environment, produce a phased brownfield import plan: discovery, mapping, import, validation, and drift stabilization. Include risk checks and rollback considerations for each phase."

---

## B) Discovery and mapping prompts

### 4) CloudFormation to Terraform type mapping prompt

"Extract every resource type from `<TEMPLATE_PATH>` and map each one to its Terraform resource type. Prefer `awscc` where supported, and use `aws` provider where `awscc` support is missing or unsuitable. Include dependency mapping notes."

### 5) Terraform Search list-block generation prompt

"Generate a `search.tfquery.hcl` file that discovers existing resources for this stack in `<REGION>`. Use Terraform Search `list` blocks for supported types and comment unsupported/problematic list types with rationale."

### 6) Provider capability verification prompt

"Verify provider support for each mapped resource type before generating import logic. Show which resources are discoverable via Terraform Search and which require manual identity resolution."

### 7) Resource grouping prompt

"Group the resources into import waves: network, security, IAM, compute, load balancing, and data. Explain import order and why that order minimizes failures."

---

## Practical sequencing prompt (copy/paste)

"Follow this sequence in `<WORKDIR>`:
1) Understand architecture from `<TEMPLATE_PATH>`, `<K8S_MANIFEST_PATH>`, and `<APP_PATH>`.
2) Build Terraform scaffold.
3) Generate and validate Search list blocks.
4) Produce resources and import blocks.
5) Resolve import identifiers.
6) Run validate/query/plan.
7) Stabilize drift with minimal safe changes.
8) Provide final checklist and next steps.

Keep everything generic and reusable. Avoid account-specific assumptions in documentation."
