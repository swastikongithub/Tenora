import { renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useRazorpayCheckout } from '../useRazorpayCheckout'

interface Opts {
  key: string
  subscription_id: string
  handler: (r: unknown) => void
  modal: { ondismiss: () => void }
}

function installFakeRazorpay() {
  let opts: Opts | undefined
  const failCbs: Array<(r: unknown) => void> = []
  class FakeRazorpay {
    constructor(o: Opts) {
      opts = o
    }
    on(_e: string, cb: (r: unknown) => void) {
      failCbs.push(cb)
    }
    open() {}
  }
  ;(window as unknown as { Razorpay: unknown }).Razorpay = FakeRazorpay
  return {
    get opts() {
      return opts
    },
    failCbs,
  }
}

const baseArgs = {
  keyId: 'k',
  subscriptionId: 's',
  planName: 'Pro',
  workspaceName: 'Acme',
  onConfirmed: vi.fn(),
  onDismissed: vi.fn(),
  onFailed: vi.fn(),
}

afterEach(() => {
  delete (window as unknown as { Razorpay?: unknown }).Razorpay
  vi.clearAllMocks()
})

describe('useRazorpayCheckout', () => {
  it('reports a loading error when checkout.js has not loaded', () => {
    const { result } = renderHook(() => useRazorpayCheckout())
    const args = { ...baseArgs }
    result.current.openCheckout(args)
    expect(args.onFailed).toHaveBeenCalledWith(
      expect.stringMatching(/still loading/i),
    )
  })

  it('passes key + subscription_id through and fires exactly one outcome', () => {
    const fake = installFakeRazorpay()
    const { result } = renderHook(() => useRazorpayCheckout())
    const args = { ...baseArgs }
    result.current.openCheckout(args)

    expect(fake.opts?.key).toBe('k')
    expect(fake.opts?.subscription_id).toBe('s')

    // Success then a late dismiss — only the first outcome counts.
    fake.opts?.handler({
      razorpay_payment_id: 'p',
      razorpay_subscription_id: 's',
      razorpay_signature: 'sig',
    })
    fake.opts?.modal.ondismiss()

    expect(args.onConfirmed).toHaveBeenCalledTimes(1)
    expect(args.onDismissed).not.toHaveBeenCalled()
  })

  it('maps a payment.failed event to onFailed with the description', () => {
    const fake = installFakeRazorpay()
    const { result } = renderHook(() => useRazorpayCheckout())
    const args = { ...baseArgs }
    result.current.openCheckout(args)

    fake.failCbs.forEach((cb) => cb({ error: { description: 'Card declined' } }))
    expect(args.onFailed).toHaveBeenCalledWith('Card declined')
  })
})
