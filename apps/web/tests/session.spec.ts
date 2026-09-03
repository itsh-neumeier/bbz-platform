import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useSessionStore } from '@/stores/session';
import * as client from '@/lib/apiClient';

beforeEach(() => {
  setActivePinia(createPinia());
  vi.restoreAllMocks();
});

describe('session store', () => {
  it('logs in, then loads permissions from /auth/me', async () => {
    const post = vi.spyOn(client.api, 'post').mockResolvedValue({
      user: { id: 'u1', display_name: 'A', status: 'active' },
      must_change_password: false,
      csrf_token: 't',
      mfa_enrolment_required: false,
      mfa_grace_until: null,
    } as never);
    const get = vi.spyOn(client.api, 'get').mockResolvedValue({
      user: { id: 'u1', display_name: 'A', status: 'active' },
      permissions: ['events.view', 'events.accept'],
      scopes: [],
    } as never);

    const s = useSessionStore();
    const factor = await s.login({ username: 'a', password: 'b' });

    expect(factor.kind).toBe('none');
    expect(s.authenticated).toBe(true);
    expect(s.can('events.accept')).toBe(true);
    expect(s.can('events.archive')).toBe(false);
    expect(post).toHaveBeenCalledWith('/auth/login', expect.objectContaining({ username: 'a' }));
    expect(get).toHaveBeenCalledWith('/auth/me');
  });

  it('surfaces a required TOTP factor instead of throwing', async () => {
    vi.spyOn(client.api, 'post').mockRejectedValue(
      new client.ApiError(401, { code: 'totp_required', message: 'second factor' }),
    );
    const s = useSessionStore();
    expect(await s.login({ username: 'a', password: 'b' })).toEqual({ kind: 'totp' });
    expect(s.authenticated).toBe(false);
  });

  it('markExpired drops the user and flags the store', () => {
    const s = useSessionStore();
    s.user = { id: 'u', display_name: 'x', status: 'active' };
    s.permissions = ['a'];
    s.markExpired();
    expect(s.user).toBeNull();
    expect(s.expired).toBe(true);
    expect(s.authenticated).toBe(false);
  });

  it('clamps the comms width to the allowed range', () => {
    const s = useSessionStore();
    s.setCommsWidth(9999);
    expect(s.commsWidth).toBe(640);
    s.setCommsWidth(10);
    expect(s.commsWidth).toBe(280);
  });
});
