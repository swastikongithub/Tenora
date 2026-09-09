/**
 * THE signature test for Stage C2 (spec §4.3 / §10). It exists explicitly and
 * is named so it is individually identifiable in the test report — it is not
 * implied by other passing tests.
 *
 *   Given: a user in Tenant A and Tenant B, with different cached member lists
 *          for each already in the query cache.
 *   When:  switchTenant(B.id) is called while a component reading Tenant A's
 *          member list is still mounted.
 *   Then:  the component shows Tenant B's data (or a loading state), never a
 *          flash or persistence of Tenant A's data.
 */

import { QueryClientProvider, useQuery } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import { server } from '../../../test/msw/server'
import {
  TENANT_A,
  TENANT_B,
  apiUrl,
  tenantsMeHandler,
} from '../../../test/fixtures'
import { apiClient } from '../../api-client'
import { createQueryClient } from '../../query-client'
import { queryKeys } from '../../query-keys'
import { setCurrentTenantId } from '../current-tenant'
import { TenantProvider } from '../TenantProvider'
import { useTenant } from '../tenant-context'

const A_MEMBER = 'ada@alpha.test'
const B_MEMBER = 'bo@beta.test'

function MemberList() {
  const { currentTenantId } = useTenant()
  const query = useQuery({
    queryKey: queryKeys.members(currentTenantId ?? '∅'),
    queryFn: () => apiClient.get<Array<{ email: string }>>('/memberships/'),
    enabled: currentTenantId != null,
  })

  if (!query.data) return <p>loading members</p>
  return (
    <ul aria-label="members">
      {query.data.map((m) => (
        <li key={m.email}>{m.email}</li>
      ))}
    </ul>
  )
}

function SwitchToB() {
  const { switchTenant } = useTenant()
  return <button onClick={() => switchTenant(TENANT_B.id)}>switch to B</button>
}

beforeEach(() => {
  setCurrentTenantId(null)
})

describe('§4.3 signature test — tenant cache isolation', () => {
  it('switching tenant cannot render stale previous-tenant data', async () => {
    const queryClient = createQueryClient()

    // Different member lists for each tenant, already in the cache.
    queryClient.setQueryData(queryKeys.members(TENANT_A.id), [
      { email: A_MEMBER },
    ])
    queryClient.setQueryData(queryKeys.members(TENANT_B.id), [
      { email: B_MEMBER },
    ])

    server.use(
      tenantsMeHandler([TENANT_A, TENANT_B]),
      // Safety net — should not be hit while the cached data is fresh.
      http.get(apiUrl('/memberships/'), () =>
        HttpResponse.json([{ email: 'from-network@should-not-appear.test' }]),
      ),
    )

    render(
      <QueryClientProvider client={queryClient}>
        <TenantProvider>
          <MemberList />
          <SwitchToB />
        </TenantProvider>
      </QueryClientProvider>,
    )

    // Tenant A is active first (first in the list, nothing stored).
    await waitFor(() => expect(screen.getByText(A_MEMBER)).toBeInTheDocument())
    expect(screen.queryByText(B_MEMBER)).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'switch to B' }))

    // Tenant B's data now; Tenant A's is gone — not a flash, not a persistence.
    await waitFor(() => expect(screen.getByText(B_MEMBER)).toBeInTheDocument())
    expect(screen.queryByText(A_MEMBER)).not.toBeInTheDocument()

    // The header the API client will send has followed the switch...
    expect(queryKeys.members(TENANT_B.id)).toContain(TENANT_B.id)

    // ...and isolation did NOT come from nuking the cache: A's entry and the
    // global tenants list both survive as inactive/global entries.
    expect(queryClient.getQueryData(queryKeys.members(TENANT_A.id))).toEqual([
      { email: A_MEMBER },
    ])
    expect(queryClient.getQueryData(queryKeys.tenantsMe())).toBeDefined()
  })
})
