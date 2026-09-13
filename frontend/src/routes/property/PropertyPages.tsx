/**
 * Owner portfolio pages: properties, units (with leases, meters, readings),
 * residents (invitations, leases, billing history) and the first-run
 * onboarding wizard. Every mutation calls a tenant-scoped endpoint; ids come
 * from this workspace's own lists and the server re-resolves them regardless.
 */

import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Alert, Badge, Button, EmptyState, Input, Modal, Table } from '../../components'
import { apiClient } from '../../lib/api-client'
import { formatDay, formatDecimal, money, toMinorRate, toMinorUnits } from '../../lib/property/format'
import { useInvalidateProperty, usePropertyQuery, useWorkspaceRole } from '../../lib/property/hooks'
import type {
  Bill,
  Invitation,
  Lease,
  Meter,
  Payment,
  Property,
  Resident,
  Unit,
  WorkspaceOverview,
  WorkspaceSettings,
  WorkspaceUsage,
} from '../../lib/property/types'
import { BillTable } from './BillTable'
import { ReadingForm } from './BillingPages'
import { ReasonModal } from './BillDetailPage'
import { OnboardingBanner } from './OnboardingBanner'
import { PageHeader, QueryState, Section, Select, StatGrid, StatTile, UsageMeter } from './ui'
import { errorMessage, fieldError } from '../../lib/property/errors'

function useCurrency() {
  return usePropertyQuery<WorkspaceSettings>('settings', '/workspace/settings/').data?.currency ?? 'INR'
}

// --- properties -----------------------------------------------------------

function PropertyForm({ onCreated }: { onCreated: (p: Property) => void }) {
  const [name, setName] = useState('')
  const [address, setAddress] = useState('')
  const [city, setCity] = useState('')
  const mutation = useMutation({
    mutationFn: () => apiClient.post<Property>('/properties/', { name, address_line_1: address, city }),
    onSuccess: (p) => {
      setName('')
      setAddress('')
      setCity('')
      onCreated(p)
    },
  })
  return (
    <form
      aria-label="Create property"
      className="grid grid-cols-1 gap-3 sm:grid-cols-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (name.trim()) mutation.mutate()
      }}
    >
      <Input label="Property name" value={name} onChange={(e) => setName(e.target.value)} error={Boolean(fieldError(mutation.error, 'name'))} helperText={fieldError(mutation.error, 'name')} />
      <Input label="Address" value={address} onChange={(e) => setAddress(e.target.value)} />
      <Input label="City" value={city} onChange={(e) => setCity(e.target.value)} />
      <div className="flex items-end">
        <Button type="submit" loading={mutation.isPending} disabled={!name.trim()}>
          Add property
        </Button>
      </div>
      {mutation.error && !fieldError(mutation.error, 'name') && (
        <div className="sm:col-span-4">
          <Alert variant="danger">{errorMessage(mutation.error)}</Alert>
        </div>
      )}
    </form>
  )
}

export function PropertiesPage() {
  const navigate = useNavigate()
  const invalidate = useInvalidateProperty()
  const { tenantName } = useWorkspaceRole()
  const properties = usePropertyQuery<Property[]>('properties', '/properties/')
  const overview = usePropertyQuery<WorkspaceOverview>('overview', '/workspace/overview/')
  return (
    <div>
      <PageHeader eyebrow={tenantName} title="Properties" description="Buildings in this workspace, their units and occupancy." />
      {overview.data && !overview.data.onboarding.ready_to_bill && <OnboardingBanner overview={overview.data} />}
      {overview.data && (
        <StatGrid>
          <StatTile label="Properties" value={overview.data.properties} />
          <StatTile label="Units" value={overview.data.units} />
          <StatTile label="Occupied units" value={overview.data.occupied_units} />
          <StatTile label="Overdue bills" value={overview.data.overdue_bills} tone={overview.data.overdue_bills ? 'danger' : undefined} />
        </StatGrid>
      )}
      <Section title="Add a property">
        <PropertyForm onCreated={() => invalidate()} />
      </Section>
      <Section title="All properties">
        <QueryState isLoading={properties.isLoading} error={properties.error} onRetry={() => properties.refetch()} label="properties" />
        {properties.data?.length === 0 && <EmptyState headline="No properties yet" description="Add your first building above." />}
        {properties.data && properties.data.length > 0 && (
          <Table
            caption="Properties"
            rows={properties.data}
            rowKey={(p) => p.id}
            onRowClick={(p) => navigate(`/properties/${p.id}`)}
            columns={[
              { key: 'name', header: 'Name', render: (p) => p.name },
              { key: 'address', header: 'Address', render: (p) => [p.address_line_1, p.city].filter(Boolean).join(', ') || '—' },
              { key: 'units', header: 'Units', numeric: true, render: (p) => p.unit_count ?? 0 },
              { key: 'occupied', header: 'Occupied', numeric: true, render: (p) => p.occupied_count ?? 0 },
              { key: 'status', header: 'Status', render: (p) => <Badge variant={p.is_active ? 'success' : 'neutral'}>{p.is_active ? 'Active' : 'Inactive'}</Badge> },
            ]}
          />
        )}
      </Section>
    </div>
  )
}

function UnitForm({ propertyId, onCreated }: { propertyId: string; onCreated: () => void }) {
  const [identifier, setIdentifier] = useState('')
  const [floor, setFloor] = useState('')
  const [unitType, setUnitType] = useState('')
  const mutation = useMutation({
    mutationFn: () => apiClient.post('/units/', { property_id: propertyId, identifier, floor, unit_type: unitType }),
    onSuccess: () => {
      setIdentifier('')
      setFloor('')
      onCreated()
    },
  })
  return (
    <form
      aria-label="Add unit"
      className="grid grid-cols-1 gap-3 sm:grid-cols-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (identifier.trim()) mutation.mutate()
      }}
    >
      <Input label="Unit number" value={identifier} onChange={(e) => setIdentifier(e.target.value)} error={Boolean(fieldError(mutation.error, 'identifier'))} helperText={fieldError(mutation.error, 'identifier')} />
      <Input label="Floor" value={floor} onChange={(e) => setFloor(e.target.value)} />
      <Input label="Type" value={unitType} onChange={(e) => setUnitType(e.target.value)} placeholder="2BHK, shop…" />
      <div className="flex items-end">
        <Button type="submit" loading={mutation.isPending} disabled={!identifier.trim()}>
          Add unit
        </Button>
      </div>
      {mutation.error && !fieldError(mutation.error, 'identifier') && (
        <div className="sm:col-span-4">
          <Alert variant="danger">{errorMessage(mutation.error)}</Alert>
        </div>
      )}
    </form>
  )
}

export function PropertyDetailPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const invalidate = useInvalidateProperty()
  const detail = usePropertyQuery<Property & { units: Unit[] }>('property', `/properties/${id}/`)
  const toggle = useMutation({
    mutationFn: (active: boolean) => apiClient.patch(`/properties/${id}/`, { is_active: active }),
    onSuccess: () => invalidate(),
  })
  if (!detail.data) return <QueryState isLoading={detail.isLoading} error={detail.error} onRetry={() => detail.refetch()} label="this property" />
  const p = detail.data
  return (
    <div>
      <p className="mb-4 text-label">
        <Link to="/properties" className="text-secondary hover:text-primary">← Properties</Link>
      </p>
      <PageHeader
        title={p.name}
        description={[p.address_line_1, p.city, p.state].filter(Boolean).join(', ') || 'No address recorded'}
        actions={
          <Button variant="secondary" size="sm" loading={toggle.isPending} onClick={() => toggle.mutate(!p.is_active)}>
            {p.is_active ? 'Deactivate' : 'Reactivate'}
          </Button>
        }
      />
      {toggle.error && <Alert variant="danger" className="mb-4">{errorMessage(toggle.error)}</Alert>}
      <Section title="Add a unit">
        <UnitForm propertyId={id} onCreated={() => invalidate()} />
      </Section>
      <Section title="Units">
        {p.units.length === 0 ? (
          <EmptyState headline="No units yet" description="Add apartments, rooms or shops above." />
        ) : (
          <Table
            caption="Units"
            rows={p.units}
            rowKey={(u) => u.id}
            onRowClick={(u) => navigate(`/units/${u.id}`)}
            columns={[
              { key: 'identifier', header: 'Unit', render: (u) => u.identifier },
              { key: 'floor', header: 'Floor', render: (u) => u.floor || '—' },
              { key: 'type', header: 'Type', render: (u) => u.unit_type || '—' },
              { key: 'status', header: 'Status', render: (u) => <Badge variant={u.status === 'OCCUPIED' ? 'success' : 'neutral'}>{u.status}</Badge> },
            ]}
          />
        )}
      </Section>
    </div>
  )
}

// --- units ----------------------------------------------------------------

function LeaseForm({ unitId, residents, onDone }: { unitId?: string; residentId?: string; residents?: Resident[]; units?: Unit[]; onDone: () => void }) {
  const [residentId, setResidentId] = useState('')
  const [start, setStart] = useState(new Date().toISOString().slice(0, 10))
  const [rent, setRent] = useState('')
  const [deposit, setDeposit] = useState('')
  const rentMinor = toMinorUnits(rent)
  const depositMinor = deposit ? toMinorUnits(deposit) : null
  const available = (residents ?? []).filter((r) => r.status === 'ACTIVE')
  const mutation = useMutation({
    mutationFn: () =>
      apiClient.post('/leases/', {
        unit_id: unitId,
        resident_id: residentId || available[0]?.id,
        start_date: start,
        monthly_rent_cents: rentMinor,
        security_deposit_cents: depositMinor,
      }),
    onSuccess: () => {
      setRent('')
      onDone()
    },
  })
  if (available.length === 0) {
    return (
      <p className="text-body text-secondary">
        No active residents yet. <Link to="/residents" className="text-accent-500 underline">Invite a resident</Link> — a lease can be created once they accept.
      </p>
    )
  }
  return (
    <form
      aria-label="Create lease"
      className="grid grid-cols-1 gap-3 sm:grid-cols-5"
      onSubmit={(e: FormEvent) => {
        e.preventDefault()
        if (rentMinor !== null) mutation.mutate()
      }}
    >
      <Select label="Resident" value={residentId || available[0]?.id} onChange={(e) => setResidentId(e.target.value)}>
        {available.map((r) => (
          <option key={r.id} value={r.id}>
            {r.display_name}
          </option>
        ))}
      </Select>
      <Input label="Start date" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
      <Input label="Monthly rent" inputMode="decimal" value={rent} onChange={(e) => setRent(e.target.value)} error={rent !== '' && rentMinor === null} />
      <Input label="Deposit (optional)" inputMode="decimal" value={deposit} onChange={(e) => setDeposit(e.target.value)} />
      <div className="flex items-end">
        <Button type="submit" loading={mutation.isPending} disabled={rentMinor === null}>
          Create lease
        </Button>
      </div>
      {mutation.error && (
        <div className="sm:col-span-5">
          <Alert variant="danger">{errorMessage(mutation.error)}</Alert>
        </div>
      )}
    </form>
  )
}

function MeterForm({ unitId, onDone }: { unitId: string; onDone: () => void }) {
  const [number, setNumber] = useState('')
  const [multiplier, setMultiplier] = useState('1')
  const mutation = useMutation({
    mutationFn: () => apiClient.post('/meters/', { unit_id: unitId, meter_number: number, multiplier }),
    onSuccess: () => {
      setNumber('')
      onDone()
    },
  })
  return (
    <form
      aria-label="Add meter"
      className="grid grid-cols-1 gap-3 sm:grid-cols-3"
      onSubmit={(e) => {
        e.preventDefault()
        if (number.trim()) mutation.mutate()
      }}
    >
      <Input label="Meter number" value={number} onChange={(e) => setNumber(e.target.value)} error={Boolean(fieldError(mutation.error, 'meter_number'))} helperText={fieldError(mutation.error, 'meter_number')} />
      <Input label="Multiplier" inputMode="decimal" value={multiplier} onChange={(e) => setMultiplier(e.target.value)} helperText="Usually 1" />
      <div className="flex items-end">
        <Button type="submit" loading={mutation.isPending} disabled={!number.trim()}>
          Add meter
        </Button>
      </div>
    </form>
  )
}

export function UnitDetailPage() {
  const { id = '' } = useParams()
  const invalidate = useInvalidateProperty()
  const currency = useCurrency()
  const detail = usePropertyQuery<Unit & { leases: Lease[]; meters: Meter[]; bills: Bill[] }>('unit', `/units/${id}/`)
  const residents = usePropertyQuery<Resident[]>('residents', '/residents/', { status: 'ACTIVE' })
  const [ending, setEnding] = useState<Lease | null>(null)
  const [endDate, setEndDate] = useState(new Date().toISOString().slice(0, 10))
  const endLease = useMutation({
    mutationFn: () => apiClient.post(`/leases/${ending?.id}/end/`, { end_date: endDate }),
    onSuccess: () => {
      setEnding(null)
      invalidate()
    },
  })
  if (!detail.data) return <QueryState isLoading={detail.isLoading} error={detail.error} onRetry={() => detail.refetch()} label="this unit" />
  const u = detail.data
  const active = u.leases.find((l) => l.status === 'ACTIVE')
  return (
    <div>
      <p className="mb-4 text-label">
        <Link to={`/properties/${u.property_id}`} className="text-secondary hover:text-primary">← {u.property_name}</Link>
      </p>
      <PageHeader title={`Unit ${u.identifier}`} description={`${u.property_name}${u.floor ? ` · Floor ${u.floor}` : ''}`} actions={<Badge variant={u.status === 'OCCUPIED' ? 'success' : 'neutral'}>{u.status}</Badge>} />

      <Section title="Lease">
        {active ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-subtle p-4">
            <div>
              <p className="text-label text-primary">
                <Link to={`/residents/${active.resident_id}`} className="underline">{active.resident_name}</Link> · {money(active.monthly_rent_cents, currency)}/month
              </p>
              <p className="text-caption text-secondary">Since {formatDay(active.start_date)}</p>
            </div>
            <Button size="sm" variant="secondary" onClick={() => setEnding(active)}>
              End lease
            </Button>
          </div>
        ) : (
          <LeaseForm unitId={id} residents={residents.data} onDone={() => invalidate()} />
        )}
        {u.leases.filter((l) => l.status !== 'ACTIVE').length > 0 && (
          <ul className="mt-3 flex flex-col gap-1 text-caption text-secondary">
            {u.leases
              .filter((l) => l.status !== 'ACTIVE')
              .map((l) => (
                <li key={l.id}>
                  {l.resident_name} · {formatDay(l.start_date)} – {formatDay(l.end_date)} · {money(l.monthly_rent_cents, currency)} · {l.status}
                </li>
              ))}
          </ul>
        )}
      </Section>

      <Section title="Meters">
        {u.meters.length > 0 && (
          <ul className="mb-3 flex flex-col gap-1">
            {u.meters.map((m) => (
              <li key={m.id} className="text-label text-primary">
                <span className="font-mono">{m.meter_number}</span> · ×{formatDecimal(m.multiplier)} ·{' '}
                {m.latest_reading ? `last ${formatDecimal(m.latest_reading.reading_value)} on ${formatDay(m.latest_reading.reading_date)}` : 'no readings yet'}
              </li>
            ))}
          </ul>
        )}
        <MeterForm unitId={id} onDone={() => invalidate()} />
        {u.meters.length > 0 && (
          <div className="mt-4">
            <ReadingForm meters={u.meters} onDone={() => invalidate()} />
          </div>
        )}
      </Section>

      <Section title="Billing history">
        {u.bills.length === 0 ? <p className="text-body text-secondary">No bills for this unit yet.</p> : <BillTable bills={u.bills} caption="Unit billing history" />}
      </Section>

      <Modal
        open={ending !== null}
        onClose={() => setEnding(null)}
        title="End lease"
        footer={
          <>
            <Button variant="ghost" onClick={() => setEnding(null)}>Cancel</Button>
            <Button variant="danger" loading={endLease.isPending} onClick={() => endLease.mutate()}>End lease</Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <p className="text-body text-secondary">The lease and every bill issued under it stay on record.</p>
          {endLease.error && <Alert variant="danger">{errorMessage(endLease.error)}</Alert>}
          <Input label="End date" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        </div>
      </Modal>
    </div>
  )
}

// --- residents & invitations -----------------------------------------------

export function InviteResidentModal({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const [email, setEmail] = useState('')
  const [unitId, setUnitId] = useState('')
  const [message, setMessage] = useState('')
  const units = usePropertyQuery<Unit[]>('units', '/units/', {}, { enabled: open })
  const mutation = useMutation({
    mutationFn: () => apiClient.post<Invitation>('/invitations/', { email, unit_id: unitId || null, message }),
    onSuccess: () => {
      setEmail('')
      setMessage('')
      onDone()
      onClose()
    },
  })
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Invite a resident"
      hasUnsavedChanges={email.trim() !== ''}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="invite-form" loading={mutation.isPending} disabled={!email.trim()}>
            Send invitation
          </Button>
        </>
      }
    >
      <form
        id="invite-form"
        className="flex flex-col gap-3"
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          mutation.mutate()
        }}
      >
        <p className="text-body text-secondary">
          They must already have a Tenora account. Nothing changes for them until they accept from their notifications —
          and a pending invitation reserves one member seat.
        </p>
        {mutation.error && !fieldError(mutation.error, 'email') && <Alert variant="danger">{errorMessage(mutation.error)}</Alert>}
        <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} error={Boolean(fieldError(mutation.error, 'email'))} helperText={fieldError(mutation.error, 'email')} />
        <Select label="Unit (optional context)" value={unitId} onChange={(e) => setUnitId(e.target.value)}>
          <option value="">No specific unit</option>
          {units.data?.map((u) => (
            <option key={u.id} value={u.id}>
              {u.identifier} · {u.property_name}
            </option>
          ))}
        </Select>
        <Input label="Message (optional)" value={message} onChange={(e) => setMessage(e.target.value)} />
      </form>
    </Modal>
  )
}

export function ResidentsPage() {
  const navigate = useNavigate()
  const invalidate = useInvalidateProperty()
  const { tenantName } = useWorkspaceRole()
  const currency = useCurrency()
  const [inviting, setInviting] = useState(false)
  const residents = usePropertyQuery<Resident[]>('residents', '/residents/')
  const invitations = usePropertyQuery<Invitation[]>('invitations', '/invitations/')
  const usage = usePropertyQuery<WorkspaceUsage>('usage', '/workspace/usage/')
  const cancel = useMutation({
    mutationFn: (inviteId: string) => apiClient.post(`/invitations/${inviteId}/cancel/`),
    onSuccess: () => invalidate(),
  })
  const atLimit = usage.data ? usage.data.members.used >= usage.data.members.limit : false
  return (
    <div>
      <PageHeader
        eyebrow={tenantName}
        title="Residents"
        description="People living in this workspace’s units. Residents join only by accepting an invitation."
        actions={
          <Button onClick={() => setInviting(true)} disabled={atLimit} title={atLimit ? 'Member limit reached' : undefined}>
            Invite resident
          </Button>
        }
      />
      {usage.data && (
        <div className="mb-6 max-w-md">
          <UsageMeter label={`Members${usage.data.plan_name ? ` · ${usage.data.plan_name}` : ''}`} used={usage.data.members.used} limit={usage.data.members.limit} />
          {usage.data.members.pending_invitations > 0 && (
            <p className="mt-1 text-caption text-secondary">Includes {usage.data.members.pending_invitations} pending invitation(s).</p>
          )}
        </div>
      )}
      <QueryState isLoading={residents.isLoading} error={residents.error} onRetry={() => residents.refetch()} label="residents" />
      {residents.data?.length === 0 && <EmptyState headline="No residents yet" description="Invite residents; they appear here once they accept." />}
      {residents.data && residents.data.length > 0 && (
        <Table
          caption="Residents"
          rows={residents.data}
          rowKey={(r) => r.id}
          onRowClick={(r) => navigate(`/residents/${r.id}`)}
          columns={[
            { key: 'name', header: 'Resident', render: (r) => r.display_name },
            { key: 'email', header: 'Email', render: (r) => r.email },
            { key: 'unit', header: 'Unit', render: (r) => (r.active_lease ? `${r.active_lease.unit_identifier} · ${r.active_lease.property_name}` : '—') },
            { key: 'rent', header: 'Rent', numeric: true, render: (r) => (r.active_lease ? money(r.active_lease.monthly_rent_cents, currency) : '—') },
            { key: 'status', header: 'Status', render: (r) => <Badge variant={r.status === 'ACTIVE' ? 'success' : 'neutral'}>{r.status === 'ACTIVE' ? 'Active' : 'Former'}</Badge> },
          ]}
        />
      )}
      <Section title="Invitations">
        {cancel.error && <Alert variant="danger" className="mb-3">{errorMessage(cancel.error)}</Alert>}
        {invitations.data?.length === 0 && <p className="text-body text-secondary">No invitations sent yet.</p>}
        <ul className="flex flex-col gap-2">
          {invitations.data?.map((inv) => (
            <li key={inv.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-subtle p-3">
              <div>
                <p className="text-label text-primary">{inv.email}</p>
                <p className="text-caption text-secondary">
                  Sent {formatDay(inv.created_at)}
                  {inv.unit_identifier ? ` · Unit ${inv.unit_identifier}` : ''}
                  {inv.status === 'PENDING' ? ` · expires ${formatDay(inv.expires_at)}` : ''}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={inv.status === 'ACCEPTED' ? 'success' : inv.status === 'PENDING' ? 'warning' : 'neutral'}>{inv.status}</Badge>
                {inv.status === 'PENDING' && (
                  <Button size="sm" variant="ghost" onClick={() => cancel.mutate(inv.id)}>
                    Cancel
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      </Section>
      <InviteResidentModal open={inviting} onClose={() => setInviting(false)} onDone={() => invalidate()} />
    </div>
  )
}

interface MembershipRow {
  id: string
  email: string
  role: string
  status: string
}

export function ResidentDetailPage() {
  const { id = '' } = useParams()
  const invalidate = useInvalidateProperty()
  const currency = useCurrency()
  const detail = usePropertyQuery<Resident & { leases: Lease[]; bills: Bill[]; payments: Payment[]; outstanding_cents: number; overdue_cents: number }>(
    'resident',
    `/residents/${id}/`,
  )
  const members = usePropertyQuery<MembershipRow[]>('memberships', '/memberships/')
  const [rentLease, setRentLease] = useState<Lease | null>(null)
  const [rent, setRent] = useState('')
  const [removing, setRemoving] = useState(false)
  const rentMinor = toMinorUnits(rent)
  const updateRent = useMutation({
    mutationFn: () => apiClient.patch(`/leases/${rentLease?.id}/`, { monthly_rent_cents: rentMinor }),
    onSuccess: () => {
      setRentLease(null)
      invalidate()
    },
  })
  if (!detail.data) return <QueryState isLoading={detail.isLoading} error={detail.error} onRetry={() => detail.refetch()} label="this resident" />
  const r = detail.data
  const membership = members.data?.find((m) => m.email === r.email && m.role === 'MEMBER')
  return (
    <div>
      <p className="mb-4 text-label">
        <Link to="/residents" className="text-secondary hover:text-primary">← Residents</Link>
      </p>
      <PageHeader
        title={r.display_name}
        description={`${r.email}${r.phone ? ` · ${r.phone}` : ''}`}
        actions={
          membership && r.status === 'ACTIVE' ? (
            <Button size="sm" variant="ghost" onClick={() => setRemoving(true)}>
              Remove from workspace
            </Button>
          ) : (
            <Badge variant="neutral">Former resident</Badge>
          )
        }
      />
      <StatGrid>
        <StatTile label="Outstanding" value={money(r.outstanding_cents, currency)} />
        <StatTile label="Overdue" value={money(r.overdue_cents, currency)} tone={r.overdue_cents ? 'danger' : undefined} />
        <StatTile label="Bills" value={r.bills.length} />
        <StatTile label="Payments" value={r.payments.filter((p) => p.status === 'COMPLETED').length} />
      </StatGrid>
      <Section title="Leases">
        {r.leases.length === 0 && <p className="text-body text-secondary">No leases. Open a vacant unit to create one.</p>}
        <ul className="flex flex-col gap-2">
          {r.leases.map((l) => (
            <li key={l.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-subtle p-3">
              <p className="text-label text-primary">
                <Link to={`/units/${l.unit_id}`} className="underline">Unit {l.unit_identifier}</Link> · {l.property_name} · {money(l.monthly_rent_cents, currency)}/month ·{' '}
                {formatDay(l.start_date)} – {l.end_date ? formatDay(l.end_date) : 'present'}
              </p>
              <div className="flex items-center gap-2">
                <Badge variant={l.status === 'ACTIVE' ? 'success' : 'neutral'}>{l.status}</Badge>
                {l.status === 'ACTIVE' && (
                  <Button size="sm" variant="ghost" onClick={() => { setRentLease(l); setRent((l.monthly_rent_cents / 100).toFixed(2)) }}>
                    Change rent
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      </Section>
      <Section title="Billing history">
        {r.bills.length === 0 ? <p className="text-body text-secondary">No bills yet.</p> : <BillTable bills={r.bills} showResident={false} caption="Resident billing history" />}
      </Section>
      <Section title="Payments">
        {r.payments.length === 0 ? (
          <p className="text-body text-secondary">No payments yet.</p>
        ) : (
          <ul className="flex flex-col gap-1 text-label">
            {r.payments.map((p) => (
              <li key={p.id}>
                {formatDay(p.payment_date)} · <span className="font-mono">{money(p.amount_cents, p.currency)}</span> · {p.method} · {p.status}
                {p.receipt_id && (
                  <>
                    {' · '}
                    <Link to={`/receipts/${p.receipt_id}`} className="text-accent-500 underline">{p.receipt_number}</Link>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Modal
        open={rentLease !== null}
        onClose={() => setRentLease(null)}
        title="Change monthly rent"
        footer={
          <>
            <Button variant="ghost" onClick={() => setRentLease(null)}>Cancel</Button>
            <Button loading={updateRent.isPending} disabled={rentMinor === null} onClick={() => updateRent.mutate()}>Save rent</Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <p className="text-body text-secondary">Applies to bills generated from now on. Issued bills keep the rent they were issued with.</p>
          {updateRent.error && <Alert variant="danger">{errorMessage(updateRent.error)}</Alert>}
          <Input label={`Monthly rent (${currency})`} inputMode="decimal" value={rent} onChange={(e) => setRent(e.target.value)} />
        </div>
      </Modal>
      <ReasonModal
        open={removing}
        title="Remove this resident?"
        confirmLabel="Remove"
        description="They lose access to this workspace immediately. Their bills, payments and receipts stay on record."
        onClose={() => setRemoving(false)}
        onConfirm={async () => {
          if (membership) await apiClient.post(`/memberships/${membership.id}/remove/`)
          await invalidate()
        }}
      />
    </div>
  )
}

// --- onboarding ------------------------------------------------------------

export function OnboardingPage() {
  const invalidate = useInvalidateProperty()
  const { tenantName } = useWorkspaceRole()
  const overview = usePropertyQuery<WorkspaceOverview>('overview', '/workspace/overview/')
  const properties = usePropertyQuery<Property[]>('properties', '/properties/')
  const [inviting, setInviting] = useState(false)
  const [rate, setRate] = useState('')
  const minorRate = toMinorRate(rate)
  const tariff = useMutation({
    mutationFn: () =>
      apiClient.post('/billing/tariffs/', { rate_per_unit_cents: minorRate, effective_from: new Date().toISOString().slice(0, 8) + '01' }),
    onSuccess: () => invalidate(),
  })
  const data = overview.data
  if (!data) return <QueryState isLoading={overview.isLoading} error={overview.error} onRetry={() => overview.refetch()} label="setup progress" />
  const done = Object.fromEntries(data.onboarding.steps.map((s) => [s.key, s.done]))
  const firstProperty = properties.data?.[0]
  return (
    <div className="max-w-[760px]">
      <PageHeader eyebrow={tenantName} title="Set up your workspace" description="Six short steps to your first monthly bills. Skip anything and come back later." />
      <OnboardingBanner overview={data} />
      <ol className="flex flex-col gap-4">
        {data.onboarding.steps.map((step, index) => (
          <li key={step.key} className="rounded-lg border border-subtle bg-raised p-4" aria-label={`Step ${index + 1}: ${step.label}`}>
            <div className="flex items-center justify-between gap-2">
              <p className="text-label font-medium text-primary">
                {index + 1}. {step.label}
              </p>
              <Badge variant={step.done ? 'success' : 'neutral'}>{step.done ? 'Done' : 'To do'}</Badge>
            </div>
            {!step.done && step.key === 'property' && (
              <div className="mt-3">
                <PropertyForm onCreated={() => invalidate()} />
              </div>
            )}
            {!step.done && step.key === 'units' && firstProperty && (
              <div className="mt-3">
                <UnitForm propertyId={firstProperty.id} onCreated={() => invalidate()} />
              </div>
            )}
            {!step.done && step.key === 'residents' && (
              <div className="mt-3">
                <Button size="sm" onClick={() => setInviting(true)}>Invite a resident</Button>
              </div>
            )}
            {!step.done && step.key === 'tariff' && (
              <form
                className="mt-3 flex flex-wrap items-end gap-3"
                onSubmit={(e) => {
                  e.preventDefault()
                  if (minorRate) tariff.mutate()
                }}
              >
                <div className="w-48">
                  <Input label="Electricity rate per unit" inputMode="decimal" value={rate} onChange={(e) => setRate(e.target.value)} />
                </div>
                <Button type="submit" size="sm" disabled={!minorRate} loading={tariff.isPending}>Save rate</Button>
                {tariff.error && <Alert variant="danger">{errorMessage(tariff.error)}</Alert>}
              </form>
            )}
            {!step.done && step.key === 'leases' && (
              <p className="mt-2 text-caption text-secondary">
                Once a resident accepts, open a unit from <Link to="/properties" className="underline">Properties</Link> and create their lease.
              </p>
            )}
          </li>
        ))}
      </ol>
      {done.leases && done.tariff && (
        <Alert variant="success" className="mt-6">
          Ready to bill. <Link to="/billing" className="underline">Start your first billing cycle</Link>.
        </Alert>
      )}
      <InviteResidentModal open={inviting} onClose={() => setInviting(false)} onDone={() => invalidate()} />
    </div>
  )
}
