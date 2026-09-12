/**
 * One error shape the whole UI renders. Every failed request from the API
 * client rejects with an `ApiError` — never a bare `Response` or a raw thrown
 * string — so a caller always has `status`, a human `message`, and per-field
 * errors where DRF provided them (Stage C2 spec §4.1).
 */

export type FieldErrors = Record<string, string[]>

export class ApiError extends Error {
  /** HTTP status, or 0 for a transport failure (network down, CORS, abort). */
  readonly status: number
  /** DRF error code when the body carried one (`{"code": "..."}`); usually absent. */
  readonly code?: string
  /** DRF field errors: `{ email: ["Already a member."] }`. Empty when none. */
  readonly fieldErrors: FieldErrors

  constructor(
    status: number,
    message: string,
    options: { code?: string; fieldErrors?: FieldErrors } = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = options.code
    this.fieldErrors = options.fieldErrors ?? {}
  }

  /** A transport-level failure — the request never got an HTTP response. */
  static network(message = 'Network request failed'): ApiError {
    return new ApiError(0, message)
  }

  /**
   * Build from a parsed response body. Understands the two shapes DRF emits:
   *   { "detail": "..." }                        (APIException / permission)
   *   { "field": ["msg", ...], "other": [...] }  (serializer validation)
   */
  static fromBody(status: number, statusText: string, body: unknown): ApiError {
    if (body && typeof body === 'object') {
      const record = body as Record<string, unknown>

      const detail = record.detail
      const code = typeof record.code === 'string' ? record.code : undefined

      const fieldErrors: FieldErrors = {}
      for (const [key, value] of Object.entries(record)) {
        // `code` is reserved for DRF's error CODE — but only when it is a
        // string, which is the only shape DRF ever emits it in. A `code` whose
        // value is a list is an ordinary serializer field error for a field
        // that happens to be named "code" (the operator plan form has exactly
        // such a field), and skipping it would silently drop the one message
        // that says what was wrong.
        if (key === 'detail') continue
        if (key === 'code' && typeof value === 'string') continue
        if (Array.isArray(value)) {
          fieldErrors[key] = value.map(String)
        } else if (typeof value === 'string') {
          fieldErrors[key] = [value]
        }
      }

      if (typeof detail === 'string') {
        return new ApiError(status, detail, { code, fieldErrors })
      }

      const firstField = Object.values(fieldErrors)[0]?.[0]
      if (firstField) {
        return new ApiError(status, firstField, { code, fieldErrors })
      }
    }

    return new ApiError(
      status,
      statusText || `Request failed with status ${status}`,
    )
  }
}
