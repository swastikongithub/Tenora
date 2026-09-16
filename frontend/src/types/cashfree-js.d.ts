/**
 * Minimal types for @cashfreepayments/cashfree-js (the package ships none).
 * Only the surface Tenora uses: load(), checkout() for P9's property-bill
 * hosted checkout, and subscriptionsCheckout() for the Tenora subscription
 * mandate. The two are different Cashfree products sharing one browser SDK.
 */
declare module '@cashfreepayments/cashfree-js' {
  export interface CashfreeCheckoutOptions {
    paymentSessionId: string
    redirectTarget?: '_self' | '_blank' | '_top' | '_modal' | HTMLElement
  }
  export interface CashfreeCheckoutResult {
    error?: { message?: string }
    redirect?: boolean
    paymentDetails?: unknown
  }
  export interface CashfreeSubscriptionCheckoutOptions {
    subsSessionId: string
    redirectTarget?: '_self' | '_blank' | '_top' | '_modal' | HTMLElement
  }
  export interface Cashfree {
    checkout(options: CashfreeCheckoutOptions): Promise<CashfreeCheckoutResult>
    subscriptionsCheckout(
      options: CashfreeSubscriptionCheckoutOptions,
    ): Promise<CashfreeCheckoutResult>
  }
  export function load(options: { mode: 'sandbox' | 'production' }): Promise<Cashfree | null>
}
