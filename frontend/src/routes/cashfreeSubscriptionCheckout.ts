/**
 * Opens Cashfree's SUBSCRIPTION checkout, where the owner authorises a
 * recurring mandate (UPI AutoPay / card / eNACH) for a Tenora plan.
 *
 * Separate from `lib/property/cashfree.ts` on purpose: that one opens a
 * one-off order for a resident's property bill. Same vendor SDK, different
 * product, different domain — neither should start behaving like the other
 * because someone edited a shared helper.
 *
 * The browser receives only an opaque session token for a mandate the server
 * created; it never sees credentials, and never decides an amount. Checkout
 * redirects this tab, and the return lands back on /subscription where the
 * SERVER — not the redirect — reports what happened.
 */

import { load } from '@cashfreepayments/cashfree-js'

export async function openCashfreeSubscriptionCheckout(
  sessionToken: string,
  mode: 'sandbox' | 'production',
): Promise<void> {
  const cashfree = await load({ mode })
  if (!cashfree) throw new Error('Checkout is unavailable in this browser.')
  const result = await cashfree.subscriptionsCheckout({
    subsSessionId: sessionToken,
    redirectTarget: '_self',
  })
  if (result?.error) {
    throw new Error(result.error.message || 'Checkout could not be opened.')
  }
}
