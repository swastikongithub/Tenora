import { describe, expect, it } from 'vitest'

import { ApiError } from '../api-error'

describe('ApiError.fromBody', () => {
  it('reads a DRF { detail } body', () => {
    const err = ApiError.fromBody(403, 'Forbidden', {
      detail: 'You are not a member of this tenant.',
    })
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(403)
    expect(err.message).toBe('You are not a member of this tenant.')
    expect(err.fieldErrors).toEqual({})
  })

  it('reads DRF serializer field errors and surfaces the first as the message', () => {
    const err = ApiError.fromBody(400, 'Bad Request', {
      email: ['A user with this email already exists.'],
      slug: ['This field is required.'],
    })
    expect(err.fieldErrors).toEqual({
      email: ['A user with this email already exists.'],
      slug: ['This field is required.'],
    })
    expect(err.message).toBe('A user with this email already exists.')
  })

  it('keeps a { code } and still prefers detail for the message', () => {
    const err = ApiError.fromBody(400, 'Bad Request', {
      detail: 'X-Tenant-ID header is required and must be a valid UUID.',
      code: 'tenant_header_invalid',
    })
    expect(err.code).toBe('tenant_header_invalid')
    expect(err.message).toContain('X-Tenant-ID')
  })

  it('treats a list-valued "code" as a field error, not as the DRF error code', () => {
    // The operator plan form posts a field literally named `code`; DRF only
    // ever emits its own error code as a string, so the two are separable by
    // shape and a plan-code validation message must survive.
    const err = ApiError.fromBody(400, 'Bad Request', {
      code: ['A plan with this code already exists.'],
    })
    expect(err.fieldErrors).toEqual({
      code: ['A plan with this code already exists.'],
    })
    expect(err.code).toBeUndefined()
    expect(err.message).toBe('A plan with this code already exists.')
  })

  it('falls back to status text, then a generic string, for a non-DRF body', () => {
    expect(ApiError.fromBody(500, 'Internal Server Error', null).message).toBe(
      'Internal Server Error',
    )
    expect(ApiError.fromBody(500, '', '<html>oops</html>').message).toBe(
      'Request failed with status 500',
    )
  })

  it('network() is a status-0 transport error', () => {
    const err = ApiError.network()
    expect(err.status).toBe(0)
    expect(err.fieldErrors).toEqual({})
  })
})
