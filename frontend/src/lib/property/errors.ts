import { ApiError } from '../api-error'

/** The message to show for a failed mutation or query. */
export function errorMessage(cause: unknown, fallback = 'Something went wrong. Try again.'): string {
  if (cause instanceof ApiError) {
    if (cause.status === 0) return 'Couldn’t reach the server. Check your connection and try again.'
    // ApiError.message is already the server's `detail` when there is one, else
    // the first field message — never a serialized extra such as a list of ids.
    if (cause.status === 403 && (!cause.message || cause.message === 'Forbidden')) {
      return 'You don’t have permission to do that.'
    }
    return cause.message || fallback
  }
  return fallback
}

export function fieldError(cause: unknown, field: string): string | undefined {
  return cause instanceof ApiError ? cause.fieldErrors[field]?.[0] : undefined
}
