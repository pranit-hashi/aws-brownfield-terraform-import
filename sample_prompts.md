# Sample Prompts for Brownfield AWS Import to Terraform

These sample prompts can be used with your preferred LLM model. Adapt them to your
environment, provider versions, constraints, and other requirements as needed. They are
provided for demonstration purposes; review and validate all generated Terraform before
using it.

## Recommended workflow

1. Use the **Master prompt** to generate a Terraform Search query file, then provide that
   file to the Search & Import feature in HCP Terraform.
2. Use the **Pre-import configuration review prompt** to review and improve the starter
   configuration produced by Search & Import before importing resources.
3. After the brownfield application is under Terraform management in a single `main.tf`,
   use the **Refactor Module prompt** to plan and carry out a modular refactor.

Run the prompts at the relevant stage; the Refactor Module prompt is intended for the
post-import stage, not for initial discovery or import.

---

## 1. Master prompt — generate a Search query

Use this prompt when starting the overall bulk import procedure. It asks the LLM to
produce the query configuration that you will feed to HCP Terraform's Search & Import
feature.

```text
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
```

## 2. Pre-import configuration review prompt

Use this prompt after Search & Import has produced its starter configuration. It focuses
on checking and polishing that configuration before import; it is read-only and requires
approval before any proposed fixes are applied.

```text
# Role
You are a Terraform expert reviewing a configuration before a bulk import. You have access to the Terraform MCP Server for official provider documentation.

### Context
- The file `main.tf` in the current working directory was generated by HCP Terraform's **Search and Import** feature.
- That feature produces a *starter configuration*, with resource attributes populated from each provider's schema. Generated configs are known to contain attributes that are invalid, conflicting, deprecated, read-only (computed-only), or wrongly typed.
- I am about to import all resources in this file into Terraform state. The config must be valid and must not cause unwanted diffs or replacements after import.

### Task
Review `main.tf` and cross-check every resource's fields and parameters against the official provider documentation, using the Terraform MCP Server. Identify anything broken or likely to break.

### Process
1. Read `main.tf` in full. List every `resource`, `data`, `provider`, and `terraform` block, with the provider name and version constraint.
2. For each distinct resource type, use the Terraform MCP Server to look up the provider docs at the version in use:
   - Resolve the provider and fetch the documentation for that specific resource type.
   - Do not rely on memory for argument names, types, or constraints. Verify each one against the docs.
3. For each resource block, check:
   - **Invalid arguments:** attributes or blocks that don't exist in the schema, or are misspelled.
   - **Computed-only attributes:** read-only fields (e.g. `arn`, `id`, `*_id` assigned by the API, timestamps) set as arguments.
   - **Missing required arguments:** required fields that are absent.
   - **Conflicts:** mutually exclusive arguments (`ConflictsWith`, `ExactlyOneOf`, `AtLeastOneOf`) set together or missing.
   - **Type and value errors:** wrong types, nested block vs. attribute syntax, invalid enum values, wrong formats.
   - **Deprecated arguments or resources:** note the recommended replacement.
   - **Hardcoded values:** account IDs, regions, or cross-resource IDs and ARNs that should be references. Flag these as warnings only, because they are not necessarily errors for an import.
   - **Import-readiness:** whether the resource type supports import, and the correct import ID format if relevant.
4. Check cross-resource references and dependencies (e.g. resource addresses, `for_each` or `count` usage, missing referenced resources).
5. If a provider's docs can't be retrieved for a resource, say so explicitly. Do not guess.

### Constraints
- **This phase is read-only.** Do NOT edit, create, or delete any files, and do not run `terraform import`, `apply`, or any command that changes state or infrastructure.
- Do not make assumptions about my intent. If something is ambiguous, list it as a question.

### Output format
Report findings as a table or list, grouped by resource address, with:
| Resource | Location (line) | Problem | Severity (Error / Warning / Info) | Proposed fix | Doc reference |

Then add:
- A short summary: total resources reviewed, and counts by severity.
- A list of any resources you could not verify, and why.
- If you found nothing wrong, say so explicitly.

### Approval gate (important)
After presenting the findings, **stop and wait for my explicit approval**. Do not modify `main.tf` until I confirm which fixes to apply. Once I approve (all or a subset), apply only the approved changes. Afterwards, run `terraform fmt` and `terraform validate` if available, and show me a diff of what changed.
```

## 3. Refactor Module prompt

Use this prompt after the imported brownfield application is managed in Terraform as a
single monolithic `main.tf`, when you are ready to refactor it into cohesive modules.
This is a demonstration prompt with example environment details and a pinned
`hashicorp/aws` version of `6.67.0`. Update provider versions, resource examples,
environment details, and assumptions to match your own configuration before using it.

```text
# Role
You are a senior Terraform engineer who refactors brownfield, imported AWS configurations
into clean, modular Terraform without changing any real infrastructure.

### Context
- Target file: `main.tf` in the current working directory. It is one monolithic file
  generated by Terraform Search + bulk import of an existing AWS three-tier app
  (VPC, subnets, NAT/IGW, route tables, security groups, IAM/IRSA, EKS, ALB, ECR, DynamoDB).
- **Every resource in `main.tf` has already been imported into state in an HCP Terraform
  workspace.** This refactor is about addresses and code layout only. The real resources
  must not change.
- Supporting files: `providers.tf` (pins `hashicorp/aws = 6.67.0`, Terraform `>= 1.14.0`)
  and `variables.tf`. Ignore `main.tf.bak`.
- The HCP Terraform workspace enforces two Sentinel policies (see `sentinel.hcl`):
  - `no-destructive-changes` (hard-mandatory): any delete or replace fails the run.
  - `flag-resource-updates` (soft-mandatory): any in-place update gets flagged.
- Tools available:
  - Local skill `terraform:refactor-module`. Load it first and follow its workflow.
  - Local skill `terraform:terraform-style-guide`. Load it and apply its naming, file
    layout, and formatting conventions.
  - Terraform MCP server (if available). Use it to check arguments, attributes, and
    `moved` block behaviour against the docs for the pinned provider version.

### Objective
Refactor `main.tf` into a modular structure that:
1. Splits resources into cohesive local child modules under `modules/`.
2. Gives every resource a meaningful logical name instead of the generated
   `stack_*_N` / `*_in_stack_*_N_M` names.
3. Replaces hard-coded IDs, ARNs, and names that point to other resources in this
   configuration with Terraform references, so dependencies are implicit.
4. Adds explicit `depends_on` only where an implicit reference can't express a
   dependency that create or destroy ordering needs.
5. Produces a plan with **0 to add, 0 to change, 0 to destroy**. The only changes allowed are moves.

### Process
1. **Inventory**: List every `resource`, `data`, and `import` block in `main.tf` with its
   current address, its `Name` tag or `name`, and what it references.
2. **Design the modules**: Propose a module layout before you write any code. A possible
   starting point (change it if the skill suggests something better):
   - `modules/network`: VPC, IGW, subnets, EIP, NAT gateway, route tables, routes, associations
   - `modules/security_groups`: security groups and their ingress rules
   - `modules/eks`: cluster IAM role, node IAM role and inline policy, launch template,
     EKS cluster, node group, OIDC provider
   - `modules/irsa`: ALB controller policy and role, app DynamoDB role and inline policy
   - `modules/alb`: target group, load balancer, listener
   - `modules/ecr`, `modules/dynamodb`
   Rules: modules must not depend on each other in a cycle. Data flows only through module
   inputs and outputs. Each module has `main.tf`, `variables.tf`, `outputs.tf`, and
   `versions.tf`, following the style guide.
   **Stop and show me the layout and the full old-to-new address mapping table. Wait for my
   approval before you continue.**
3. **Rename the logical names**: Derive each name from the resource's role (its `Name` tag,
   description, or AZ), in snake_case and without repeating the resource type. Use `this`
   for the single resource of its type in a module. Examples:
   - `aws_vpc.stack_vpcs_0` → `module.network.aws_vpc.this`
   - `aws_subnet.stack_subnets_3` (`demo-public-subnet-1`, ap-southeast-1a) → `module.network.aws_subnet.public_a`
   - `aws_route.routes_in_stack_route_tables_1_1` (0.0.0.0/0 via NAT) → `module.network.aws_route.private_nat`
   - `aws_iam_role.iam_roles_33` → `module.irsa.aws_iam_role.alb_controller`
   You may merge same-type resources into `for_each` with stable string keys, but only if
   it makes the code clearer. Every instance then needs its own `moved` block. If you're
   unsure, keep them as separate resources.
4. **Preserve state with `moved` blocks**:
   - Add one `moved { from = <old address> to = <new module address> }` per resource, in a
     root-level `moved.tf`.
   - Remove the `import` blocks. Their resources are already in state. Import blocks can't
     go inside child modules, and an import block left pointing at an old address would
     conflict with the moves. List the removed import IDs in your summary for traceability.
5. **Replace the hard-coded cross-references**: Find every literal that matches an ID, ARN,
   or name managed in this configuration. Replace it with a reference, or with a module
   output passed in as an input. Known cases (the list is not complete, so do your own
   search):
   - The private NAT route has `route_table_id = "rtb-0e706131230807a4c"`. Reference the
     private route table instead.
   - The node role inline policy hard-codes the DynamoDB table ARN and the `/index/*` ARN.
     Use the table's `arn` attribute.
   - The app DynamoDB inline policy builds its ARNs from `var.dynamodb_table_name` and the
     caller identity. Use the table's `arn` attribute.
   - The OIDC provider `url` is a literal. Derive it from the EKS cluster's
     `identity[0].oidc[0].issuer`.
   - The subnet tags `kubernetes.io/cluster/demo-eks-cluster` hard-code the cluster name.
     Referencing the cluster here would create a cycle, because the cluster depends on
     the subnets. Use a shared `cluster_name` input or local instead.
   - Leave real external constants (AWS service principals, managed policy ARNs, CIDRs)
     as literals or variables.
   A reference must resolve to **exactly** the value that's there now. If it wouldn't,
   keep the literal and flag it.
6. **Add explicit dependencies**: Add `depends_on` only for ordering that no attribute
   reference captures, and add a one-line comment on each to explain why. Check these
   candidates and justify each one you add or skip:
   - EIP and NAT gateway → internet gateway (the IGW must be attached first; it's removed last)
   - Internet-facing ALB → internet gateway / public default route
   - EKS node group → node IAM role policy, private NAT route and route table
     associations (nodes need egress to join the cluster), and the node SG ingress rules
   - IRSA roles → OIDC provider (probably implicit already, so confirm)
   Prefer dependencies at the resource level, passed through module outputs. Avoid
   module-level `depends_on` unless nothing else works, and explain why if you use it.
   Don't add `depends_on` when there's already an implicit reference.
7. **Clean up the code**: Apply the style guide. Remove `provider = aws` lines that add
   nothing, arguments explicitly set to `null`, and `timeouts {}` blocks that only
   contain `null` values. Only remove something if it causes no plan diff. Move
   environment-specific values into variables with descriptions and types. Add
   `outputs.tf` at the root for the key IDs and ARNs.
8. **Validate**: Run `terraform fmt -recursive`, `terraform init`, and
   `terraform validate`. If a backend or HCP Terraform workspace is configured locally,
   run `terraform plan` (speculative, read-only) and confirm that every resource shows as
   moved and the result is `0 to add, 0 to change, 0 to destroy`. If you can't run a plan,
   say so. I will check it with a speculative plan in HCP Terraform.
   Repeat steps 3–8 until validate passes and the plan, if available, is clean.

### Constraints
- Never run `terraform apply`, `import`, `state mv`, `state rm`, `destroy`, or anything else
  that writes to state or AWS.
- Don't change any argument value that would alter real infrastructure. Any
  replacement or update that shows up in the plan is a bug in the refactor, so fix it.
- Every argument, attribute, and block must exist in the pinned `hashicorp/aws 6.67.0`
  schema. Never guess.
- Don't add resources that are missing from the current config (for example, EKS
  managed policy attachments). List them as open items instead.
- Don't commit or push unless I ask.
- If something is ambiguous (naming, module boundaries, whether a literal is external),
  stop and ask.

### Output
Reply with:
1. **Module tree**: the final directory structure.
2. **Address mapping table**: Old address | New address | Module | `moved` block added (Y/N)
3. **Reference replacements table**: Resource | Argument | Old literal | New reference
4. **Explicit dependencies table**: Resource | `depends_on` target | Reason (include the
   candidates you rejected, and why)
5. **Removed import blocks**: address and import ID
6. **Validation results**: `fmt`, `validate`, and the `plan` summary (or why you couldn't run it)
7. **Open items**: missing resources, external dependencies, and questions for me

### Definition of done
`terraform validate` passes. Every resource lives in a module under a meaningful name and
has a matching `moved` block. No literals that point to resources in this configuration
are left. Every `depends_on` has a justification comment. The plan, if run, shows only
moves: 0 to add, 0 to change, 0 to destroy.
```
