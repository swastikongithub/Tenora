/**
 * Add-member form, in a Modal (§C.4 Page 3). A single email field, POSTed to
 * `/api/memberships/` — which adds an *existing* user to the current tenant as
 * MEMBER.
 *
 * There is deliberately NO role field. The endpoint only ever assigns MEMBER
 * (master spec §A.4.15 / B1); a role selector would imply a capability the API
 * does not have. `tenant_id` is never in the body either — the tenant comes from
 * the `X-Tenant-ID` header, and the api-client's `assertNoTenantInBody` guard
 * enforces it.
 *
 * Error handling mirrors `CreateWorkspaceModal`:
 *   - `{email: [...]}` (409-style duplicate, or an invalid address) → inline
 *     field error, modal stays open, the entered email is preserved.
 *   - 404 `{detail}` (no such user) → inline field error on email, using the
 *     detail text (the backend shapes unknown-email as a detail, not a field
 *     error, but §C.4 wants it shown against the field).
 *   - 403 → a form-level alert (a MEMBER reaching here via a stale render — the
 *     server is the real boundary; we just don't crash).
 */

import { useEffect, useState, type FormEvent } from 'react'

import { Alert, Button, Input, Modal } from '../components'
import { apiClient } from '../lib/api-client'
import { ApiError } from '../lib/api-error'
import type { Member } from './MembersPage'

const FORM_ID = 'add-member-form'

interface AddMemberModalProps {
  open: boolean
  onClose: () => void
  onAdded: (member: Member) => void
}

export function AddMemberModal({ open, onClose, onAdded }: AddMemberModalProps) {
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [emailError, setEmailError] = useState<string | undefined>()
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setEmail('')
    setSubmitting(false)
    setEmailError(undefined)
    setFormError(null)
  }, [open])

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setEmailError(undefined)
    setFormError(null)
    setSubmitting(true)
    try {
      const member = await apiClient.post<Member>('/memberships/', { email })
      onAdded(member)
    } catch (cause) {
      setSubmitting(false)
      if (cause instanceof ApiError) {
        if (cause.fieldErrors.email?.length) {
          setEmailError(cause.fieldErrors.email[0])
          return
        }
        if (cause.status === 404) {
          setEmailError(cause.message)
          return
        }
        if (cause.status === 403) {
          setFormError(
            'You don’t have permission to add members to this workspace.',
          )
          return
        }
        if (cause.status === 0) {
          setFormError(
            'Couldn’t reach the server. Check your connection and try again.',
          )
          return
        }
      }
      setFormError('The server had a problem adding that member. Try again.')
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Add member"
      hasUnsavedChanges={email.trim() !== ''}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" form={FORM_ID} loading={submitting}>
            Add member
          </Button>
        </>
      }
    >
      <form
        id={FORM_ID}
        onSubmit={onSubmit}
        className="flex flex-col gap-4"
        noValidate
      >
        {formError && <Alert variant="danger">{formError}</Alert>}
        <Input
          label="Email"
          name="email"
          type="email"
          autoComplete="off"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={submitting}
          error={Boolean(emailError)}
          helperText={
            emailError ?? 'The person must already have an account.'
          }
          autoFocus
          required
        />
      </form>
    </Modal>
  )
}
