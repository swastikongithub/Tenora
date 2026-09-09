import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { CancelSubscriptionModal } from '../CancelSubscriptionModal'

function setup(overrides: Partial<Parameters<typeof CancelSubscriptionModal>[0]> = {}) {
  const onConfirm = vi.fn()
  const onClose = vi.fn()
  const props = {
    open: true,
    workspaceName: 'Alpha Corp',
    submitting: false,
    error: null as string | null,
    onConfirm,
    onClose,
    ...overrides,
  }
  render(<CancelSubscriptionModal {...props} />)
  return {
    onConfirm,
    onClose,
    confirmButton: () =>
      screen.getByRole('button', { name: 'Cancel subscription' }),
    field: () => screen.getByLabelText(/to confirm/i),
  }
}

describe('CancelSubscriptionModal — type-to-confirm gate', () => {
  it('keeps the destructive button disabled until the workspace name is typed exactly', async () => {
    const { confirmButton, field } = setup()
    expect(confirmButton()).toBeDisabled()

    await userEvent.type(field(), 'Alpha Cor') // near miss
    expect(confirmButton()).toBeDisabled()

    await userEvent.type(field(), 'p') // now "Alpha Corp"
    expect(confirmButton()).toBeEnabled()

    await userEvent.clear(field())
    expect(confirmButton()).toBeDisabled()
  })

  it('tolerates leading/trailing whitespace but not a wrong-case match', async () => {
    const { confirmButton, field } = setup()

    await userEvent.type(field(), '  Alpha Corp  ')
    expect(confirmButton()).toBeEnabled()

    await userEvent.clear(field())
    await userEvent.type(field(), 'alpha corp')
    expect(confirmButton()).toBeDisabled()
  })

  it('fires onConfirm only once the gate is satisfied', async () => {
    const { confirmButton, field, onConfirm } = setup()

    await userEvent.click(confirmButton()) // disabled — no-op
    expect(onConfirm).not.toHaveBeenCalled()

    await userEvent.type(field(), 'Alpha Corp')
    await userEvent.click(confirmButton())
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('closes via "Keep subscription" and via Escape', async () => {
    const { onClose } = setup()

    await userEvent.click(screen.getByRole('button', { name: 'Keep subscription' }))
    expect(onClose).toHaveBeenCalledTimes(1)

    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('renders a server error handed back by the page', () => {
    setup({ error: 'Cannot transition from CANCELED to CANCELED.' })
    expect(
      screen.getByText('Cannot transition from CANCELED to CANCELED.'),
    ).toBeInTheDocument()
  })

  it('states the real consequence and does not promise a new subscription later', () => {
    setup()
    const dialog = screen.getByRole('dialog', { name: 'Cancel subscription' })
    expect(dialog).toHaveTextContent(/permanently cancels/i)
    expect(dialog).toHaveTextContent(/no reactivation/i)
    // No invented payment/refund/access-loss claims (spec §1 / §4.4).
    expect(dialog).not.toHaveTextContent(/refund/i)
    expect(dialog).not.toHaveTextContent(/lose access/i)
  })
})
