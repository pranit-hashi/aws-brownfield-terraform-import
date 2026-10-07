# Helper Prompts for Brownfield AWS Import to Terraform

> Note: These are sample prompts intended for reference only. You should tune and adapt them to your own environment, constraints, and delivery requirements.

> Important: LLM outputs vary by model, model version, temperature/settings, and runtime context. Two runs may not produce identical results, even with the same prompt. Always review, test, and validate generated output before using it in production.

Use these prompts when working with a LLM model to follow the brownfield import guide in this directory. These are intentionally generic and reusable across AWS environments.

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

### Role
You are a Terraform engineer experienced with AWS, CloudFormation, and Terraform Search (`list` blocks in `.tfquery.hcl` files, Terraform >= 1.14).

### Context
- Source of truth: the CloudFormation template `three-tier-app.yaml` in the current working directory.
- Most resources created by this stack carry the AWS-managed tag
  `aws:cloudformation:stack-name = "three-tier-app"`. Some resources may not carry it, either because the resource type doesn't support tags or because tags don't propagate to it.
- Tools available:
  - Local skill `terraform:terraform-search-import`. Load it first and follow its conventions.
  - Terraform MCP server. Use it to look up the official Terraform Registry documentation for providers and list resources.

### Objective
Generate the Terraform Search query configuration needed to discover every resource defined in `three-tier-app.yaml`, so it can later be bulk-imported into Terraform. Do NOT generate resource blocks, import blocks, or any other Terraform configuration beyond what is listed under "Deliverables".

### Process
1. **Inventory**: Parse `three-tier-app.yaml` and list every resource (logical ID + `Type`). Note which ones support tags and which ones the template tags explicitly.
2. **Map each resource to a list resource**:
   a. Map each CloudFormation type to its Terraform resource type in the `hashicorp/aws` provider.
   b. Use the Terraform MCP server to check whether the latest `hashicorp/aws` provider offers
      a **list resource** for that type. Check the registry docs; don't rely on memory.
   c. If, and only if, `aws` has no list resource for it, check `hashicorp/awscc` the same way and use that instead.
   d. If neither provider supports it, don't invent one. Record it as unsupported.
3. **Filter by tag**: For each `list` block, filter on
   `aws:cloudformation:stack-name = "three-tier-app"` using the filter or config arguments that the list resource's documentation shows. Filters are only supported for aws provider. Don't use it for awscc provider. If a list resource can't filter by tag,
   or the resource isn't tagged, use the narrowest documented alternative filter
   (e.g., VPC ID, name prefix, parent resource). Add an HCL comment that explains
   why you used it.
4. **Generate files** (see Deliverables), following the skill's conventions and the
   Terraform style guide.
5. **Validate**: Run `terraform init` and `terraform validate` (and `terraform query`
   if credentials are available). Fix any errors. Do not run `plan` or `apply`,
   and do not make any changes to AWS.

### Deliverables
1. `providers.tf`: a `terraform` block with `required_version` and `required_providers`(pinned version constraints for `aws`, plus `awscc` only if it's used), and a `provider`block for each provider. Region comes from a variable; no hardcoded credentials.
2. `variables.tf`: inputs such as `region` and `stack_name` (default `"three-tier-app"`).
3. `search.tfquery.hcl`: one `list` block per discoverable resource type. Use descriptive labels, `include_resource = true` where supported, and the`stack_name` variable instead of a hardcoded tag value.
4. A summary in your reply (not in a file) with:
   - A table: CFN logical ID | CFN type | Terraform list resource | provider (`aws`/`awscc`) | filter used
   - Resources that couldn't be covered, with the reason
   - Any assumptions you made

### Constraints
- Prefer `aws` over `awscc`. Use `awscc` only as a documented fallback.
- Every list resource and argument must exist in the registry docs you looked up. Never guess.
- Avoid duplicate `list` blocks: one list resource can cover several CFN resources of the same type.
- If something is ambiguous (e.g., the template is missing, or the tag key is unusable as a filter), stop and ask rather than assume.

### Definition of done
Every resource in the template is either covered by a validated `list` block or listed as
unsupported with a reason, and `terraform validate` passes.
 ensuring resource names, types, and dependencies are correctly mapped."

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
