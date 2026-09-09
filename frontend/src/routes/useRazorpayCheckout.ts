/**
 * Opens Razorpay Checkout in subscription mode (stage-d2-spec.md §4.3).
 *
 * The `checkout.js` script tag lives in index.html (a deliberate CDN exception,
 * like the Google Identity script). This hook polls for `window.Razorpay` the
 * same way `GoogleSignInButton` polls for `window.google` — the script is
 * `async`, so it may not be parsed yet at mount.
 *
 * The hook does NOT talk to our backend. The caller creates the Razorpay
 * subscription first (`POST /subscriptions/current/checkout/`), passes the
 * returned ids here, and handles the callbacks:
 *   - `onConfirmed(payload)` — Checkout's success handler fired. The caller
 *     POSTs `payload` to `/confirm-checkout/` and shows an honest "processing"
 *     state (NOT "active" — local status hasn't changed and won't until D3).
 *   - `onDismissed()` — the user closed Checkout without paying. No state change.
 *   - `onFailed(message)` — a payment attempt failed.
 */

import { useCallback, useEffect, useState } from 'react'

export interface CheckoutSuccessPayload {
  razorpay_payment_id: string
  razorpay_subscription_id: string
  razorpay_signature: string
}

interface OpenCheckoutArgs {
  keyId: string
  subscriptionId: string
  planName: string
  workspaceName: string
  onConfirmed: (payload: CheckoutSuccessPayload) => void
  onDismissed: () => void
  onFailed: (message: string) => void
}

interface RazorpayInstance {
  open: () => void
  on: (event: 'payment.failed', handler: (resp: unknown) => void) => void
}

interface RazorpayOptions {
  key: string
  subscription_id: string
  name: string
  description: string
  handler: (response: CheckoutSuccessPayload) => void
  modal: { ondismiss: () => void }
  theme: { color?: string }
}

type RazorpayConstructor = new (options: RazorpayOptions) => RazorpayInstance

function getRazorpay(): RazorpayConstructor | undefined {
  return (window as unknown as { Razorpay?: RazorpayConstructor }).Razorpay
}

function failureMessage(resp: unknown): string {
  const err = (resp as { error?: { description?: string } } | undefined)?.error
  return err?.description || 'The payment could not be completed. Please try again.'
}

export function useRazorpayCheckout() {
  const [ready, setReady] = useState(() => Boolean(getRazorpay()))

  useEffect(() => {
    if (ready) return
    const id = window.setInterval(() => {
      if (getRazorpay()) {
        setReady(true)
        window.clearInterval(id)
      }
    }, 100)
    return () => window.clearInterval(id)
  }, [ready])

  const openCheckout = useCallback((args: OpenCheckoutArgs) => {
    const Razorpay = getRazorpay()
    if (!Razorpay) {
      args.onFailed(
        'Checkout is still loading. Check your connection and try again.',
      )
      return
    }

    let settled = false
    const settle = (fn: () => void) => {
      if (settled) return
      settled = true
      fn()
    }

    const rzp = new Razorpay({
      key: args.keyId,
      subscription_id: args.subscriptionId,
      name: args.workspaceName,
      description: `${args.planName} plan`,
      handler: (response) => settle(() => args.onConfirmed(response)),
      modal: { ondismiss: () => settle(args.onDismissed) },
      theme: {},
    })
    rzp.on('payment.failed', (resp) =>
      settle(() => args.onFailed(failureMessage(resp))),
    )
    rzp.open()
  }, [])

  return { ready, openCheckout }
}
