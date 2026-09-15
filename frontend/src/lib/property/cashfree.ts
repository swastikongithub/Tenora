/**
 * Opens Cashfree hosted checkout for a payment session our backend created.
 *
 * The browser never sees credentials or amounts it could influence: it only
 * receives an opaque `payment_session_id` for an order whose amount the server
 * fixed. Cashfree.js is loaded on first use (the loader injects the official
 * sdk.cashfree.com script), so nothing payment-related ships with the rest of
 * the app. Checkout redirects this tab; the return URL brings the resident back
 * to the bill, where the server — not this redirect — reports the outcome.
 */

import { load } from '@cashfreepayments/cashfree-js'

export async function openCashfreeCheckout(paymentSessionId: string, mode: 'sandbox' | 'production'): Promise<void> {
  const cashfree = await load({ mode })
  if (!cashfree) throw new Error('Checkout is unavailable in this browser.')
  const result = await cashfree.checkout({ paymentSessionId, redirectTarget: '_self' })
  if (result?.error) throw new Error(result.error.message || 'Checkout could not be opened.')
}
