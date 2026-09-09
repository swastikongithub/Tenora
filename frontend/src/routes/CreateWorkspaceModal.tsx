/**
 * Create-workspace form, in a Modal (§C.4 Page 2). Name + slug, POSTed to
 * `/api/tenants/` (a global path — authenticated, no `X-Tenant-ID`; no tenant
 * exists yet). `tenant_id` is never in the body — the API client's
 * `assertNoTenantInBody` guard also enforces this (§6).
 *
 * A duplicate slug comes back as `{"slug": ["…"]}` and renders as an inline
 * field error on the slug input — not a toast (the UI spec's stated pattern for
 * this exact case). The slug's format hint is bound via `aria-describedby`
 * (Input wires `helperText` to it).
 *
 * On success the parent (`WorkspacePage`) primes the tenant-list cache with the
 * new workspace and selects it through `TenantProvider.switchTenant` — this
 * component does not touch tenant state directly.
 */

import { useEffect, useState, type FormEvent } from 'react'

import { Alert, Button, Input, Modal } from '../components'
import { apiClient } from '../lib/api-client'
import { ApiError } from '../lib/api-error'
import type { TenantMembership } from '../lib/tenant'

const FORM_ID = 'create-workspace-form'

interface CreateWorkspaceModalProps {
  open: boolean
  onClose: () => void
  onCreated: (tenant: TenantMembership) => void
}

export function CreateWorkspaceModal({
  open,
  onClose,
  onCreated,
}: CreateWorkspaceModalProps) {
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<{
    name?: string
    slug?: string
  }>({})
  const [formError, setFormError] = useState<string | null>(null)

  // Fresh state every time the modal opens.
  useEffect(() => {
    if (!open) return
    setName('')
    setSlug('')
    setSubmitting(false)
    setFieldErrors({})
    setFormError(null)
  }, [open])

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFieldErrors({})
    setFormError(null)
    setSubmitting(true)
    try {
      const tenant = await apiClient.post<TenantMembership>('/tenants/', {
        name,
        slug,
      })
      onCreated(tenant)
    } catch (cause) {
      setSubmitting(false)
      if (cause instanceof ApiError && Object.keys(cause.fieldErrors).length) {
        setFieldErrors({
          name: cause.fieldErrors.name?.[0],
          slug: cause.fieldErrors.slug?.[0],
        })
        return
      }
      setFormError(
        cause instanceof ApiError && cause.status === 0
          ? 'Couldn’t reach the server. Check your connection and try again.'
          : 'The server had a problem creating that workspace. Try again.',
      )
    }
  }

  const hasInput = name.trim() !== '' || slug.trim() !== ''

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Create workspace"
      hasUnsavedChanges={hasInput}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" form={FORM_ID} loading={submitting}>
            Create workspace
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
          label="Name"
          name="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={submitting}
          error={Boolean(fieldErrors.name)}
          helperText={fieldErrors.name}
          autoFocus
          required
        />
        <Input
          label="Slug"
          name="slug"
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          disabled={submitting}
          error={Boolean(fieldErrors.slug)}
          helperText={
            fieldErrors.slug ??
            'Lowercase letters, numbers and hyphens. Appears in URLs.'
          }
          required
        />
      </form>
    </Modal>
  )
}
