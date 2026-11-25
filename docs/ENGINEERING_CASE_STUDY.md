# Booking: scheduling constraints and refundable balances

This source implements salon/spa operations with multi-item appointments, rooms,
master schedules and payment records. The useful engineering evidence is in the
boundaries where a convenient interface alone cannot guarantee consistency.

## Half-open reservations preserve back-to-back appointments

An appointment item has a start and end time, including the service's extra time.
Two reservations that meet at one boundary should share a room; reservations with
actual overlapping occupancy should conflict. The
[PostgreSQL exclusion constraint](../core/migrations/0047_half_open_room_overlap_constraint.py)
uses half-open intervals. [Existing tests](../core/tests/test_appointmentitem_overlap.py)
accept back-to-back items and reject a real overlap even when application validation
is bypassed. [Room-allocation tests](../core/tests/test_room_allocation.py) cover
available room assignment and exhausted capacity.

The database constraint protects a narrower invariant than the entire booking
workflow. Eligibility, staff shifts, service requirements and customer communication
remain application-level responsibilities. PostgreSQL is required; a passing
SQLite helper test does not prove exclusion or transaction behavior.

## Missing status history still means occupied

A new appointment can have no status-history row. A subquery then returns SQL
`NULL`; applying only `NOT status = cancelled` can silently remove it from the
availability query. Explicit `IS NULL OR NOT cancelled` predicates keep those
appointments active. The PostgreSQL allocation and master-overlap tests caught
this defect when the business suite was first enabled; the fix changes neither
stored history nor database constraints.

Cancellation has a separate boundary: the existing database room exclusion is
unconditional. An admin helper can ignore a staged cancelled row, but that alone
does not prove an overlapping active row can be persisted into its occupied room.
The helper test keeps the proposed active item unsaved. Any change to database
cancellation/reallocation policy needs a separate migration review.

## Refund allocation preserves payment ownership

[RefundService](../core/services/refunds.py) allocates a requested amount against
eligible existing payments and their remaining refundable amounts. The
[refund regressions](../core/tests/test_refunds.py) exercise partial allocation,
multiple cards and error boundaries with mocked Stripe and receipt rendering.
[Stripe API tests](../core/tests/test_stripe_api.py) separately cover metadata and
booking/payment state contracts.

A local allocation and an acknowledged external refund are different states.
Provider-side idempotency, ambiguous network outcomes and configured webhook
verification must remain explicit; these tests do not move money or certify a
live Stripe account.

## Verify without provider credentials

The [PostgreSQL business CI](../ci/README.md#postgresql-business-regressions) runs
real migrations and selected business modules against a disposable local service.
Provider secrets are cleared, email/cache/queues are local, media is temporary and
external socket connections are blocked. Test fixtures are synthetic. The existing
focused source checks remain separate; neither job claims all-module coverage.

This is a supporting scheduling/commerce example. Client ownership, coauthor
attribution and third-party licences are preserved; no production data or live
payment demonstration is published.
