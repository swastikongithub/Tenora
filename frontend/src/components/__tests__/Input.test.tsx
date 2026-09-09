import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Input } from '../Input'

describe('Input', () => {
  it('associates the label with the field', () => {
    render(<Input label="Billing email" />)
    expect(screen.getByLabelText('Billing email')).toBeInstanceOf(
      HTMLInputElement,
    )
  })

  it('does not set aria-invalid or aria-describedby in the resting state', () => {
    render(<Input label="Name" helperText="Your full name." />)
    const field = screen.getByLabelText('Name')
    expect(field).not.toHaveAttribute('aria-invalid')
  })

  it('wires aria-invalid and aria-describedby to the helper element on error', () => {
    render(
      <Input label="Email" error helperText="Enter a valid email address." />,
    )
    const field = screen.getByLabelText('Email')
    expect(field).toHaveAttribute('aria-invalid', 'true')

    const describedBy = field.getAttribute('aria-describedby')
    expect(describedBy).toBeTruthy()

    const helper = document.getElementById(describedBy!)
    expect(helper).toHaveTextContent('Enter a valid email address.')
  })

  it('only renders helper text when provided', () => {
    const { container, rerender } = render(<Input label="Name" />)
    expect(container.querySelector('p')).toBeNull()
    rerender(<Input label="Name" helperText="Required." />)
    expect(screen.getByText('Required.')).toBeInTheDocument()
  })
})
