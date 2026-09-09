/**
 * Stage C3b §9: a render-without-error check for every C1/C1a primitive under
 * `data-theme="light"`. Not a visual regression suite — it asserts the component
 * still mounts and still shows its required content after the theme switch, i.e.
 * nothing depends on a dark-only token being present. The measured contrast
 * report (docs/ui-design-specification.md §C.1) covers the colour side.
 */

import { render, screen } from '@testing-library/react'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Input,
  Modal,
  Skeleton,
  Table,
} from '../index'

beforeAll(() => {
  document.documentElement.setAttribute('data-theme', 'light')
})

afterAll(() => {
  document.documentElement.removeAttribute('data-theme')
})

describe('primitives under data-theme="light"', () => {
  it('Button — all variants render with their label', () => {
    render(
      <>
        <Button variant="primary">Save</Button>
        <Button variant="secondary">Cancel</Button>
        <Button variant="ghost">More</Button>
        <Button variant="danger">Delete</Button>
      </>,
    )
    for (const label of ['Save', 'Cancel', 'More', 'Delete']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    }
  })

  it('Input — label, value and helper text survive', () => {
    render(<Input label="Email" defaultValue="a@b.c" helperText="We never share it" />)
    expect(screen.getByLabelText('Email')).toHaveValue('a@b.c')
    expect(screen.getByText('We never share it')).toBeInTheDocument()
  })

  it('Table — headers and cells render', () => {
    render(
      <Table
        caption="Plans"
        columns={[
          { key: 'name', header: 'Name' },
          { key: 'seats', header: 'Seats', numeric: true },
        ]}
        rows={[{ name: 'Pro', seats: 5 }]}
        rowKey={(r) => r.name}
      />,
    )
    expect(screen.getByRole('columnheader', { name: 'Name' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'Pro' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '5' })).toBeInTheDocument()
  })

  it('Card — plain and featured both render their content', () => {
    render(
      <>
        <Card title="Plain">plain body</Card>
        <Card featured title="Featured">featured body</Card>
      </>,
    )
    expect(screen.getByText('plain body')).toBeInTheDocument()
    expect(screen.getByText('featured body')).toBeInTheDocument()
  })

  it('Badge — every status variant keeps its label', () => {
    render(
      <>
        <Badge variant="success">Active</Badge>
        <Badge variant="warning">Trialing</Badge>
        <Badge variant="danger">Past due</Badge>
        <Badge variant="neutral">Canceled</Badge>
        <Badge variant="accent">Owner</Badge>
      </>,
    )
    for (const label of ['Active', 'Trialing', 'Past due', 'Canceled', 'Owner']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('Modal — renders title and body when open', () => {
    render(
      <Modal open onClose={() => {}} title="Confirm">
        modal body
      </Modal>,
    )
    expect(screen.getByRole('dialog', { name: 'Confirm' })).toBeInTheDocument()
    expect(screen.getByText('modal body')).toBeInTheDocument()
  })

  it('Skeleton — keeps its accessible loading label', () => {
    render(<Skeleton label="Loading plans" count={3} />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading plans')
  })

  it('EmptyState — headline, description and action render', () => {
    render(
      <EmptyState
        headline="No workspaces yet"
        description="Create one to get started."
        action={<Button>Create workspace</Button>}
      />,
    )
    expect(screen.getByText('No workspaces yet')).toBeInTheDocument()
    expect(screen.getByText('Create one to get started.')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Create workspace' }),
    ).toBeInTheDocument()
  })

  it('Alert — every variant renders its message', () => {
    render(
      <>
        <Alert variant="info">info msg</Alert>
        <Alert variant="success">success msg</Alert>
        <Alert variant="warning">warning msg</Alert>
        <Alert variant="danger">danger msg</Alert>
      </>,
    )
    for (const msg of ['info msg', 'success msg', 'warning msg', 'danger msg']) {
      expect(screen.getByText(msg)).toBeInTheDocument()
    }
  })
})
