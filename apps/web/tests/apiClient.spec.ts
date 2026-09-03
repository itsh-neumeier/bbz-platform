import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  api,
  apiRequest,
  ApiError,
  AuthExpiredError,
  ConflictError,
  markAuthenticated,
} from '@/lib/apiClient';

function res(status: number, body: unknown, ok = status < 400): Response {
  return {
    status,
    ok,
    text: () => Promise.resolve(body === undefined ? '' : JSON.stringify(body)),
  } as unknown as Response;
}

beforeEach(() => {
  markAuthenticated(false);
  document.cookie = 'bbz_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
});

describe('apiRequest', () => {
  it('sends cookies and no command headers on a GET', async () => {
    const f = vi.fn().mockResolvedValue(res(200, { ok: true }));
    await apiRequest('/meta', { fetchImpl: f });
    const [, init] = f.mock.calls[0];
    expect(init.credentials).toBe('include');
    expect(init.headers['X-Command-Id']).toBeUndefined();
  });

  it('adds X-Command-Id and the CSRF header on a write', async () => {
    document.cookie = 'bbz_csrf=tok123';
    const f = vi.fn().mockResolvedValue(res(200, {}));
    await api.post('/events', { title: 'x' }, { fetchImpl: f, expectedVersion: 3 });
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('/api/v1/events');
    expect(init.method).toBe('POST');
    expect(init.headers['X-Command-Id']).toMatch(/.+/);
    expect(init.headers['X-Expected-Version']).toBe('3');
    expect(init.headers['X-CSRF-Token']).toBe('tok123');
  });

  it('maps the error envelope to ApiError', async () => {
    const f = vi.fn().mockResolvedValue(res(403, { error: { code: 'forbidden', message: 'nope' } }));
    await expect(apiRequest('/x', { fetchImpl: f })).rejects.toMatchObject({
      name: 'ApiError',
      status: 403,
      code: 'forbidden',
    });
  });

  it('maps 409 to ConflictError with expected_version', async () => {
    const f = vi
      .fn()
      .mockResolvedValue(
        res(409, { error: { code: 'conflict', message: 'stale', details: { expected_version: 7 } } }),
      );
    const err = await apiRequest('/x', { method: 'POST', fetchImpl: f }).catch((e) => e);
    expect(err).toBeInstanceOf(ConflictError);
    expect((err as ConflictError).expectedVersion).toBe(7);
  });

  it('maps 401 to AuthExpiredError only when a session was established', async () => {
    const f = vi.fn().mockResolvedValue(res(401, { error: { code: 'unauthorized', message: 'x' } }));
    await expect(apiRequest('/x', { fetchImpl: f })).rejects.toBeInstanceOf(ApiError);
    markAuthenticated(true);
    await expect(apiRequest('/x', { fetchImpl: f })).rejects.toBeInstanceOf(AuthExpiredError);
  });

  it('returns undefined on 204', async () => {
    const f = vi.fn().mockResolvedValue(res(204, undefined));
    await expect(apiRequest('/x', { method: 'DELETE', fetchImpl: f })).resolves.toBeUndefined();
  });
});
