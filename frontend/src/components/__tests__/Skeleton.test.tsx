import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Skeleton } from '../Skeleton'

describe('Skeleton', () => {
  it('exposes an accessible loading status', () => {
    render(<Skeleton label="Loading members" />)
    const status = screen.getByRole('status')
    expect(status).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByText('Loading members')).toBeInTheDocument()
  })

  it('renders one block per count', () => {
    const { container } = render(<Skeleton count={4} />)
    const blocks = container.querySelectorAll('[aria-hidden="true"]')
    expect(blocks).toHaveLength(4)
  })

  it('applies numeric width/height as pixel values', () => {
    const { container } = render(<Skeleton width={200} height={24} />)
    const block = container.querySelector('[aria-hidden="true"]') as HTMLElement
    expect(block.style.width).toBe('200px')
    expect(block.style.height).toBe('24px')
  })
})
