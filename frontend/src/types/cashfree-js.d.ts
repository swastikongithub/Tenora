/**
 * Minimal types for @cashfreepayments/cashfree-js (the package ships none).
 * Only the surface Tenora uses: load() + checkout() for hosted checkout.
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
  export interface Cashfree {
    checkout(options: CashfreeCheckoutOptions): Promise<CashfreeCheckoutResult>
  }
  export function load(options: { mode: 'sandbox' | 'production' }): Promise<Cashfree | null>
}
