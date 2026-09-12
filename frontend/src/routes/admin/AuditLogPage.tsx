/**
 * /admin/audit-log — docs/operator-control-plane-spec.md's own phase plan
 * assigns the AuditEvent model and its write paths to Phase 2 (critical vs.
 * observational audit semantics), not Phase 1. There is nothing to read yet.
 *
 * The route exists now — part of the canonical /admin IA — but makes no
 * backend request: there is no GET /api/platform/audit-log/ in Phase 1, and
 * building one against a model that doesn't exist would be exactly the kind
 * of ahead-of-spec backend work this phase avoids. This page is honest about
 * that rather than silently omitting the route or fabricating data.
 */

import { Card } from '../../components'

export function AuditLogPage() {
  return (
    <div>
      <h2 className="text-h2 text-primary">Audit Log</h2>
      <Card className="mt-4">
        <p className="text-body text-secondary">
          Audit logging isn’t available yet. It ships in Phase 2 alongside the
          mutation endpoints it records — this page will list every critical
          platform action once that lands.
        </p>
      </Card>
    </div>
  )
}
