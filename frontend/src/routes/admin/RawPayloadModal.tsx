/**
 * The Root-only raw gateway payload view — Phase 4 of
 * docs/operator-control-plane-spec.md §B "Webhook management — normalized
 * surface, isolated raw diagnostic".
 *
 * Every other webhook surface in this app shows Tenora's own normalized
 * fields. This one shows what the provider actually sent, because that is what
 * a diagnosis sometimes needs — and a provider payload can carry customer
 * contact and payment-instrument metadata, which is why it is Root-gated and
 * why opening it is logged server-side.
 *
 * It fetches on open, not with the list: the payload is never part of a list
 * response, and a viewing that never happened should not be recorded as one.
 */

import { useQuery } from '@tanstack/react-query'

import { Alert, Button, Modal } from '../../components'
import { apiClient } from '../../lib/api-client'
import { queryKeys } from '../../lib/query-keys'

interface RawEvent {
  id: string
  external_event_id: string
  event_type: string
  raw_payload: unknown
}

interface RawPayloadModalProps {
  open: boolean
  eventId: string | null
  onClose: () => void
}

export function RawPayloadModal({ open, eventId, onClose }: RawPayloadModalProps) {
  const raw = useQuery({
    queryKey: queryKeys.platformWebhookEventRaw(eventId ?? ''),
    queryFn: () =>
      apiClient.get<RawEvent>(`/platform/webhook-events/raw/?id=${eventId}`),
    enabled: open && Boolean(eventId),
    // A diagnostic read, and each read is audited — so it should not be
    // replayed from cache minutes later under the impression it is live.
    staleTime: 0,
    gcTime: 0,
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Raw gateway payload"
      size="detail"
      footer={
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
      }
    >
      <div className="flex flex-col gap-4">
        <Alert variant="warning">
          Root-only diagnostic. This is the provider’s own payload and can
          contain customer contact and payment-instrument metadata. Opening it
          is recorded in the audit log.
        </Alert>

        {raw.isPending ? (
          <p className="text-body text-secondary" role="status">
            Loading raw payload…
          </p>
        ) : raw.isError ? (
          <Alert variant="danger">Couldn’t load the raw payload.</Alert>
        ) : raw.data ? (
          <>
            <p className="font-mono text-caption text-secondary">
              {raw.data.external_event_id} · {raw.data.event_type}
            </p>
            <pre className="max-h-[50vh] overflow-auto rounded-md border border-subtle bg-raised p-4 font-mono text-caption text-primary">
              {JSON.stringify(raw.data.raw_payload, null, 2)}
            </pre>
          </>
        ) : null}
      </div>
    </Modal>
  )
}
