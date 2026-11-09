# Cart Recovery

A local synthetic-store operations application for the supplied abandoned-cart workflow.
Operators inspect carts and reasons; analysts reconcile credited orders and revenue; managers
coordinate recovery and review exceptions. Customer actions and email/SMS delivery are simulated.

Success: a reviewer generates/imports reproducible data, runs a normal recovery, demonstrates
withdrawal suppression and late purchase, inspects attribution and anomaly evidence, and exports
validation results. No real customer information or real delivery is used.

Platform: responsive web, FastAPI/PostgreSQL. Assumed visual direction: restrained operations
console for desktop work with usable narrow-screen access. Functional requirements come from
the user's brief; visual choices are implementation defaults. Mode: Operate.
