import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { Modal } from '../Modal'

function Harness({
  hasUnsavedChanges = false,
  onClose,
}: {
  hasUnsavedChanges?: boolean
  onClose?: () => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button onClick={() => setOpen(true)}>Open</button>
      <Modal
        open={open}
        onClose={() => {
          onClose?.()
          setOpen(false)
        }}
        title="Rename workspace"
        hasUnsavedChanges={hasUnsavedChanges}
        footer={<button>Save</button>}
      >
        <label>
          Name
          <input aria-label="Name" />
        </label>
      </Modal>
    </>
  )
}

describe('Modal', () => {
  it('labels the dialog with its title', async () => {
    render(<Harness />)
    await userEvent.click(screen.getByRole('button', { name: 'Open' }))
    expect(
      screen.getByRole('dialog', { name: 'Rename workspace' }),
    ).toHaveAttribute('aria-modal', 'true')
  })

  it('moves focus into the dialog on open and returns it to the trigger on close', async () => {
    render(<Harness />)
    const trigger = screen.getByRole('button', { name: 'Open' })
    await userEvent.click(trigger)

    const dialog = screen.getByRole('dialog')
    expect(dialog.contains(document.activeElement)).toBe(true)

    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(document.activeElement).toBe(trigger)
  })

  it('closes on Escape', async () => {
    const onClose = vi.fn()
    render(<Harness onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: 'Open' }))
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('traps Tab focus inside the dialog', async () => {
    render(<Harness />)
    await userEvent.click(screen.getByRole('button', { name: 'Open' }))
    const dialog = screen.getByRole('dialog')

    // Tab many times — focus must never leave the dialog subtree.
    for (let i = 0; i < 8; i++) {
      await userEvent.tab()
      expect(dialog.contains(document.activeElement)).toBe(true)
    }
    for (let i = 0; i < 8; i++) {
      await userEvent.tab({ shift: true })
      expect(dialog.contains(document.activeElement)).toBe(true)
    }
  })

  it('backdrop click closes when there are no unsaved changes', async () => {
    const onClose = vi.fn()
    render(<Harness onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: 'Open' }))
    await userEvent.click(screen.getByTestId('modal-backdrop'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('backdrop click does NOT close when unsaved changes are present', async () => {
    const onClose = vi.fn()
    render(<Harness hasUnsavedChanges onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: 'Open' }))
    await userEvent.click(screen.getByTestId('modal-backdrop'))
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('renders nothing when closed', () => {
    render(<Harness />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
