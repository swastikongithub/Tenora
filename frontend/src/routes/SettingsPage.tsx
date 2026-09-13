/**
 * /settings — the one canonical Settings route, role-aware (plan §14.1, §21).
 *
 *   everyone   Profile · Security · Notifications · Memberships · Manage account
 *   owner      + Workspace profile & billing defaults · Plan & subscription
 *
 * User-level settings (profile, password, notification preferences, account
 * deletion) call global /api/account/ and /api/notifications/ endpoints;
 * workspace-level ones call the tenant-scoped /api/workspace/ endpoints for the
 * ACTIVE workspace only. Hiding a section is presentation — every endpoint
 * enforces the same role server-side.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { Alert, Badge, Button, Input, Modal } from '../components'
import { apiClient } from '../lib/api-client'
import { useAuth } from '../lib/auth'
import { money, toMinorUnits } from '../lib/property/format'
import { useInvalidateProperty, usePropertyQuery, useWorkspaceRole } from '../lib/property/hooks'
import type { AccountProfile, AccountUsage, WorkspaceSettings } from '../lib/property/types'
import { queryKeys } from '../lib/query-keys'
import { useTenant } from '../lib/tenant'
import { PageHeader, QueryState, Select, UsageMeter } from './property/ui'
import { errorMessage, fieldError } from '../lib/property/errors'

function Panel({ id, title, description, children }: { id: string; title: string; description?: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="rounded-lg border border-subtle bg-raised p-5">
      <h2 id={`${id}-title`} className="text-lg font-medium text-primary">
        {title}
      </h2>
      {description && <p className="mt-1 text-body text-secondary">{description}</p>}
      <div className="mt-4">{children}</div>
    </section>
  )
}

function ProfilePanel() {
  const queryClient = useQueryClient()
  const profile = useQuery({ queryKey: queryKeys.accountProfile(), queryFn: () => apiClient.get<AccountProfile>('/account/profile/') })
  const [form, setForm] = useState({ first_name: '', last_name: '', phone: '' })
  useEffect(() => {
    if (profile.data) setForm({ first_name: profile.data.first_name, last_name: profile.data.last_name, phone: profile.data.phone })
  }, [profile.data])
  const save = useMutation({
    mutationFn: () => apiClient.patch<AccountProfile>('/account/profile/', form),
    onSuccess: (data) => queryClient.setQueryData(queryKeys.accountProfile(), data),
  })
  return (
    <Panel id="profile" title="Profile" description="Your personal details. Your email is your sign-in identity.">
      <QueryState isLoading={profile.isLoading} error={profile.error} label="your profile" />
      {profile.data && (
        <form
          className="grid grid-cols-1 gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate()
          }}
        >
          <Input label="Email" value={profile.data.email} disabled />
          <Input label="Phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} error={Boolean(fieldError(save.error, 'phone'))} helperText={fieldError(save.error, 'phone')} />
          <Input label="First name" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
          <Input label="Last name" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
          <div className="flex items-center gap-3 sm:col-span-2">
            <Button type="submit" loading={save.isPending}>Save profile</Button>
            {save.isSuccess && <span className="text-caption text-success">Saved.</span>}
          </div>
        </form>
      )}
    </Panel>
  )
}

function SecurityPanel() {
  const profile = useQuery({ queryKey: queryKeys.accountProfile(), queryFn: () => apiClient.get<AccountProfile>('/account/profile/') })
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const change = useMutation({
    mutationFn: () => apiClient.post('/account/password/', { current_password: current, new_password: next }),
    onSuccess: () => {
      setCurrent('')
      setNext('')
    },
  })
  const hasPassword = profile.data?.has_usable_password ?? true
  return (
    <Panel id="security" title="Security" description={hasPassword ? 'Change your password.' : 'You sign in with Google. You can also set a password.'}>
      <form
        className="grid grid-cols-1 gap-3 sm:grid-cols-2"
        onSubmit={(e: FormEvent) => {
          e.preventDefault()
          change.mutate()
        }}
      >
        {hasPassword && (
          <Input
            label="Current password"
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            error={Boolean(fieldError(change.error, 'current_password'))}
            helperText={fieldError(change.error, 'current_password')}
          />
        )}
        <Input
          label="New password"
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          error={Boolean(fieldError(change.error, 'new_password'))}
          helperText={fieldError(change.error, 'new_password')}
        />
        <div className="flex items-center gap-3 sm:col-span-2">
          <Button type="submit" loading={change.isPending} disabled={!next}>Update password</Button>
          {change.isSuccess && <span className="text-caption text-success">Password updated.</span>}
        </div>
      </form>
    </Panel>
  )
}

function NotificationPreferencesPanel() {
  const queryClient = useQueryClient()
  const prefs = useQuery({
    queryKey: queryKeys.notificationPreferences(),
    queryFn: () => apiClient.get<Record<string, boolean>>('/notifications/preferences/'),
  })
  const save = useMutation({
    mutationFn: (changes: Record<string, boolean>) => apiClient.patch<Record<string, boolean>>('/notifications/preferences/', changes),
    onSuccess: (data) => queryClient.setQueryData(queryKeys.notificationPreferences(), data),
  })
  const options: Array<[string, string]> = [
    ['billing', 'Bills — published, due soon, overdue, corrected'],
    ['payments', 'Payments and receipts'],
    ['membership', 'Membership updates (joins, departures)'],
  ]
  return (
    <Panel id="notifications" title="Notifications" description="In-app notifications. Workspace invitations are always shown, because you accept them from there.">
      <QueryState isLoading={prefs.isLoading} error={prefs.error} label="preferences" />
      {prefs.data && (
        <ul className="flex flex-col gap-2">
          {options.map(([key, label]) => (
            <li key={key}>
              <label className="flex items-center gap-3 text-body text-primary">
                <input type="checkbox" checked={Boolean(prefs.data[key])} onChange={(e) => save.mutate({ [key]: e.target.checked })} />
                {label}
              </label>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}

function WorkspaceSettingsPanel() {
  const invalidate = useInvalidateProperty()
  const settings = usePropertyQuery<WorkspaceSettings>('settings', '/workspace/settings/')
  const [form, setForm] = useState<Record<string, string>>({})
  useEffect(() => {
    if (settings.data) {
      setForm({
        display_name: settings.data.display_name,
        contact_email: settings.data.contact_email,
        contact_phone: settings.data.contact_phone,
        address: settings.data.address,
        receipt_footer: settings.data.receipt_footer,
        currency: settings.data.currency,
        due_days_after_period_end: String(settings.data.due_days_after_period_end),
        maintenance: (settings.data.default_maintenance_cents / 100).toFixed(2),
      })
    }
  }, [settings.data])
  const maintenance = toMinorUnits(form.maintenance ?? '0')
  const save = useMutation({
    mutationFn: () =>
      apiClient.patch('/workspace/settings/', {
        display_name: form.display_name,
        contact_email: form.contact_email,
        contact_phone: form.contact_phone,
        address: form.address,
        receipt_footer: form.receipt_footer,
        currency: form.currency,
        due_days_after_period_end: Number(form.due_days_after_period_end),
        default_maintenance_cents: maintenance ?? 0,
      }),
    onSuccess: () => invalidate(),
  })
  const set = (key: string) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value })
  return (
    <Panel id="workspace" title="Workspace profile & billing defaults" description="Shown on bills and receipts. Defaults apply to bills generated from now on — issued bills never change.">
      <QueryState isLoading={settings.isLoading} error={settings.error} label="workspace settings" />
      {settings.data && (
        <form
          className="grid grid-cols-1 gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate()
          }}
        >
          {save.error && !fieldError(save.error, 'currency') && (
            <div className="sm:col-span-2"><Alert variant="danger">{errorMessage(save.error)}</Alert></div>
          )}
          <Input label="Display name" value={form.display_name ?? ''} onChange={set('display_name')} />
          <Input label="Contact email" value={form.contact_email ?? ''} onChange={set('contact_email')} error={Boolean(fieldError(save.error, 'contact_email'))} helperText={fieldError(save.error, 'contact_email')} />
          <Input label="Contact phone" value={form.contact_phone ?? ''} onChange={set('contact_phone')} />
          <Input label="Address" value={form.address ?? ''} onChange={set('address')} />
          <Input label="Receipt footer" value={form.receipt_footer ?? ''} onChange={set('receipt_footer')} />
          <Select label="Billing currency" value={form.currency ?? 'INR'} onChange={set('currency')} error={Boolean(fieldError(save.error, 'currency'))} helperText={fieldError(save.error, 'currency') ?? 'Locked once bills exist.'}>
            {['INR', 'USD', 'EUR', 'GBP', 'AED', 'SGD'].map((c) => <option key={c} value={c}>{c}</option>)}
          </Select>
          <Input label="Due days after period end" type="number" min={0} max={90} value={form.due_days_after_period_end ?? ''} onChange={set('due_days_after_period_end')} />
          <Input label="Default maintenance charge" inputMode="decimal" value={form.maintenance ?? ''} onChange={set('maintenance')} error={maintenance === null} helperText={maintenance !== null ? `Added to each bill: ${money(maintenance, form.currency || 'INR')}` : 'Enter an amount'} />
          <div className="flex items-center gap-3 sm:col-span-2">
            <Button type="submit" loading={save.isPending} disabled={maintenance === null}>Save workspace settings</Button>
            {save.isSuccess && <span className="text-caption text-success">Saved.</span>}
          </div>
        </form>
      )}
    </Panel>
  )
}

function PlanPanel() {
  const usage = useQuery({ queryKey: queryKeys.accountUsage(), queryFn: () => apiClient.get<AccountUsage>('/account/usage/') })
  return (
    <Panel id="plan" title="Plan & subscription" description="Your Tenora plan limits. This is what you pay Tenora — separate from your residents' bills.">
      <QueryState isLoading={usage.isLoading} error={usage.error} label="plan usage" />
      {usage.data && (
        <div className="flex flex-col gap-4">
          <p className="text-body text-primary">
            Plan: <strong>{usage.data.plan_name ?? 'Basic (no active subscription)'}</strong>
          </p>
          <UsageMeter label="Workspaces" used={usage.data.workspaces.used} limit={usage.data.workspaces.limit} />
          {usage.data.owned_workspaces.map((w) => (
            <UsageMeter key={w.id} label={`${w.name} · members`} used={w.members.used} limit={w.members.limit} />
          ))}
          <Link to="/subscription" className="text-label text-accent-500 underline">Manage subscription</Link>
        </div>
      )}
    </Panel>
  )
}

interface MemberRow {
  id: string
  email: string
  role: string
}

function MembershipsPanel() {
  const { tenants, currentTenant, refetch } = useTenant()
  const { isOwner } = useWorkspaceRole()
  const queryClient = useQueryClient()
  const members = usePropertyQuery<MemberRow[]>('memberships', '/memberships/', {}, { enabled: isOwner })
  const [confirm, setConfirm] = useState<null | 'leave' | 'close' | 'transfer'>(null)
  const [target, setTarget] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const residents = (members.data ?? []).filter((m) => m.role === 'MEMBER')
  async function run() {
    setBusy(true)
    setError(null)
    try {
      if (confirm === 'leave') await apiClient.post('/memberships/leave/')
      if (confirm === 'close') await apiClient.post('/workspace/close/')
      if (confirm === 'transfer') await apiClient.post(`/memberships/${target || residents[0]?.id}/transfer-ownership/`)
      setConfirm(null)
      await queryClient.invalidateQueries({ queryKey: queryKeys.tenantsMe() })
      await queryClient.invalidateQueries({ queryKey: queryKeys.accountUsage() })
      refetch()
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setBusy(false)
    }
  }
  const copy = {
    leave: {
      title: `Leave ${currentTenant?.name ?? 'this workspace'}?`,
      body: 'You lose access to this workspace immediately. Your Tenora account stays, and your past bills and receipts remain on record with the owner. You can create your own workspace afterwards.',
      cta: 'Leave workspace',
    },
    close: {
      title: `Close ${currentTenant?.name ?? 'this workspace'}?`,
      body: 'Only possible once no other members remain. Pending invitations are cancelled and nobody can open the workspace again. Its billing history is retained.',
      cta: 'Close workspace',
    },
    transfer: {
      title: 'Transfer ownership',
      body: 'The resident you choose becomes the owner (subject to their own plan limit). You become a member and can then leave.',
      cta: 'Transfer ownership',
    },
  }
  return (
    <Panel id="memberships" title="Memberships" description="Workspaces you belong to. Leaving a workspace does not delete your account.">
      <ul className="flex flex-col gap-2">
        {tenants.map((t) => (
          <li key={t.id} className="flex items-center justify-between gap-2 text-body">
            <span className="text-primary">{t.name}</span>
            <Badge variant={t.role === 'OWNER' ? 'accent' : 'neutral'}>{t.role === 'OWNER' ? 'Owner' : 'Resident'}</Badge>
          </li>
        ))}
        {tenants.length === 0 && <li className="text-body text-secondary">You’re not in any workspace.</li>}
      </ul>
      {currentTenant && (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={() => { setError(null); setConfirm('leave') }}>
            Leave {currentTenant.name}
          </Button>
          {isOwner && residents.length > 0 && (
            <Button variant="secondary" size="sm" onClick={() => { setError(null); setConfirm('transfer') }}>
              Transfer ownership
            </Button>
          )}
          {isOwner && (
            <Button variant="ghost" size="sm" onClick={() => { setError(null); setConfirm('close') }}>
              Close workspace
            </Button>
          )}
        </div>
      )}
      <Modal
        open={confirm !== null}
        onClose={() => setConfirm(null)}
        title={confirm ? copy[confirm].title : ''}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(null)} disabled={busy}>Cancel</Button>
            <Button variant={confirm === 'transfer' ? 'primary' : 'danger'} loading={busy} onClick={run}>
              {confirm ? copy[confirm].cta : ''}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          {confirm && <p className="text-body text-secondary">{copy[confirm].body}</p>}
          {error && <Alert variant="danger">{error}</Alert>}
          {confirm === 'transfer' && (
            <Select label="New owner" value={target || residents[0]?.id} onChange={(e) => setTarget(e.target.value)}>
              {residents.map((m) => <option key={m.id} value={m.id}>{m.email}</option>)}
            </Select>
          )}
        </div>
      </Modal>
    </Panel>
  )
}

function DeleteAccountPanel() {
  const { logout } = useAuth()
  const profile = useQuery({ queryKey: queryKeys.accountProfile(), queryFn: () => apiClient.get<AccountProfile>('/account/profile/') })
  const [open, setOpen] = useState(false)
  const [confirmation, setConfirmation] = useState('')
  const del = useMutation({
    mutationFn: () => apiClient.post('/account/delete/', { confirmation }),
    onSuccess: () => {
      void logout()
    },
  })
  const blockers = profile.data?.deletion_blockers ?? []
  return (
    <Panel id="account" title="Manage account" description="Deleting your account is permanent and different from leaving a workspace.">
      {blockers.length > 0 && (
        <Alert variant="warning" className="mb-3">
          You own {blockers.map((b) => b.name).join(', ')}. Transfer ownership or close {blockers.length === 1 ? 'it' : 'them'} before deleting your account.
        </Alert>
      )}
      <Button variant="danger" onClick={() => setOpen(true)} disabled={blockers.length > 0}>
        Delete account
      </Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Delete your account?"
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="danger"
              loading={del.isPending}
              disabled={confirmation.trim().toLowerCase() !== (profile.data?.email ?? '').toLowerCase()}
              onClick={() => del.mutate()}
            >
              Permanently delete
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <p className="text-body text-secondary">
            You’ll be signed out everywhere and your memberships end. Your personal details are removed; bills, payments and
            receipts already issued stay on record for the property owner, as financial records require. This can’t be undone.
          </p>
          {del.error && <Alert variant="danger">{errorMessage(del.error)}</Alert>}
          <Input label={`Type ${profile.data?.email ?? 'your email'} to confirm`} value={confirmation} onChange={(e) => setConfirmation(e.target.value)} autoComplete="off" />
        </div>
      </Modal>
    </Panel>
  )
}

export function SettingsPage() {
  const { isOwner, tenantName } = useWorkspaceRole()
  const sections = [
    ['profile', 'Profile'],
    ['security', 'Security'],
    ['notifications', 'Notifications'],
    ...(isOwner ? [['workspace', 'Workspace & billing'], ['plan', 'Plan & subscription']] : []),
    ['memberships', 'Memberships'],
    ['account', 'Manage account'],
  ]
  return (
    <div className="max-w-[880px]">
      <PageHeader eyebrow={tenantName} title="Settings" />
      <nav aria-label="Settings sections" className="mb-6 flex flex-wrap gap-3 text-label">
        {sections.map(([id, label]) => (
          <a key={id} href={`#${id}`} className="text-secondary hover:text-primary">
            {label}
          </a>
        ))}
      </nav>
      <div className="flex flex-col gap-5">
        <ProfilePanel />
        <SecurityPanel />
        <NotificationPreferencesPanel />
        {isOwner && <WorkspaceSettingsPanel />}
        {isOwner && <PlanPanel />}
        <MembershipsPanel />
        <DeleteAccountPanel />
      </div>
    </div>
  )
}
