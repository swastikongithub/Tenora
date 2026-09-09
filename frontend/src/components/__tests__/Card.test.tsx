import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Card } from '../Card'

describe('Card', () => {
  it('renders the plain surface treatment by default', () => {
    const { container } = render(<Card>Body</Card>)
    const root = container.firstElementChild as HTMLElement

    expect(root).toHaveClass('bg-raised', 'shadow-card')
    expect(root).not.toHaveClass('bg-featured')
    expect(root).not.toHaveClass('shadow-accent-glow')
  })

  it('featured swaps in the gradient background and accent glow', () => {
    const { container } = render(<Card featured>Body</Card>)
    const root = container.firstElementChild as HTMLElement

    // §C.1a: gradient + glow replace the plain bg-raised + shadow-card combo.
    expect(root).toHaveClass('bg-featured', 'shadow-accent-glow')
    expect(root).not.toHaveClass('shadow-card')
  })

  it('featured leaves radius, padding, border and the header slot unchanged', () => {
    const plain = render(<Card title="Plan">Body</Card>)
    const plainRoot = plain.container.firstElementChild as HTMLElement
    plain.unmount()

    const { container } = render(
      <Card featured title="Plan" actions={<button>Change</button>}>
        Body
      </Card>,
    )
    const featuredRoot = container.firstElementChild as HTMLElement

    for (const shared of ['rounded-lg', 'border', 'border-subtle', 'p-6']) {
      expect(plainRoot).toHaveClass(shared)
      expect(featuredRoot).toHaveClass(shared)
    }
    // Header slot still renders title + actions when featured.
    expect(screen.getByRole('heading', { name: 'Plan' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Change' })).toBeInTheDocument()
  })
})
