# E4C Upgrade Smoke Testing

## Purpose
This smoke test is a safety check before sharing any upgraded module with the client.

It creates real test data inside an Odoo test transaction, runs the main Sales Order to Dispatch flow, and rolls everything back after the test ends.

## When To Run
Run this every time before pushing or after upgrading these modules:

- `tf_container_tracking`
- `tf_container_tracking_extends`

## Command
From `/opt/odoo19/e4c`:

```bash
./scripts/run_upgrade_smoke_tests.sh e4c
```

For another database:

```bash
./scripts/run_upgrade_smoke_tests.sh e4c-demo-data
./scripts/run_upgrade_smoke_tests.sh odoo19
```

## What It Tests
The smoke test checks these critical areas:

1. Required database fields exist after upgrade.
2. Sales Order views open without Owl/view errors.
3. Container serials are generated in readable format, for example `S00090-C01`.
4. Case serials are generated against containers, for example `S00090-1 1 of 2`.
5. Common case attributes are applied to all assigned case lines.
6. Sales Order confirmation and approval work.
7. Receiving operation creates stock lots/serials correctly.
8. Inventory truck-out from selected serials creates:
   - internal transfer,
   - delivery order,
   - dispatch ticket.
9. Dispatch WhatsApp manual tracking works.
10. Dispatch in-progress and completion flow works.
11. Trailer location updates when dispatch is completed.
12. Internal Transfer lot/serial dropdown is filtered by Sales Order.
13. Direct Container to Client flow creates only the outgoing delivery and dispatch ticket.
14. Direct Container to Client flow does not create unnecessary incoming/internal warehouse moves.

## Pass Result
If the script ends with this line, the smoke test passed:

```text
Smoke tests passed for database: <database-name>
```

## Fail Result
If the script fails, do not share the module with the client.

Read the first error in the Odoo log. That first error is usually the real cause.

## Recommended Deployment Gate
Before client delivery:

1. Take database backup.
2. Upgrade modules on staging.
3. Run this smoke test on staging database.
4. Run the full targeted module test suite.
5. Open Sales, Inventory, Container Tracking, Dispatch, and Lots/Serial Numbers once from the UI.
6. Only then move to client-visible environment.

## Full Targeted Test Command
Use this when we need stronger confidence than smoke testing only:

```bash
/opt/odoo19/venv/bin/python /opt/odoo19/odoo/odoo-bin \
  -c /etc/odoo19.conf \
  -d e4c \
  -u tf_container_tracking,tf_container_tracking_extends \
  --test-enable \
  --test-tags /tf_container_tracking,/tf_container_tracking_extends \
  --stop-after-init \
  --no-http
```
