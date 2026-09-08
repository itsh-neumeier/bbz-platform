import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useSoftphoneStore } from '@/stores/softphone';
import { ApiError } from '@/lib/apiClient';
import * as tel from '@/lib/telephony';
import * as sp from '@/lib/softphone';
import type { SoftphoneEngine, SoftphoneEvent } from '@/lib/softphone';

const CREDS: tel.WebrtcCredentials = {
  ws_url: 'wss://sip.bbz.example:8089/ws',
  sip_uri: 'sip:op-abc@sip.bbz.example',
  auth_user: 'op-abc',
  auth_password: 'secret',
  ice_servers: [{ urls: 'stun:stun.bbz.example:3478' }],
};

/** a fake engine that lets the test drive events */
function fakeEngine() {
  let emit: (e: SoftphoneEvent) => void = () => {};
  const engine: SoftphoneEngine = {
    connect: vi.fn(async (_creds, onEvent) => {
      emit = onEvent;
    }),
    setMuted: vi.fn(),
    disconnect: vi.fn(),
  };
  return { engine, fire: (e: SoftphoneEvent) => emit(e) };
}

beforeEach(() => {
  setActivePinia(createPinia());
  vi.restoreAllMocks();
  vi.spyOn(sp, 'webRtcAudioAvailable').mockReturnValue(true);
});

// the engine is a module-level singleton (a JsSIP UA can't live in reactive
// state) — clear it between tests
afterEach(() => useSoftphoneStore().stop());

describe('softphone store', () => {
  it('stays off silently when the operator has no endpoint (404)', async () => {
    vi.spyOn(tel.telephonyApi, 'webrtcCredentials').mockRejectedValue(
      new ApiError(404, { code: 'not_found', message: 'no softphone' }),
    );
    const store = useSoftphoneStore();
    await store.start();
    expect(store.state).toBe('off');
    expect(store.active).toBe(false);
    expect(store.error).toBeNull();
  });

  it('reports unsupported when the browser cannot do WebRTC', async () => {
    vi.spyOn(tel.telephonyApi, 'webrtcCredentials').mockResolvedValue(CREDS);
    vi.spyOn(sp, 'webRtcAudioAvailable').mockReturnValue(false);
    const store = useSoftphoneStore();
    await store.start(() => fakeEngine().engine);
    expect(store.state).toBe('unsupported');
    expect(store.active).toBe(true);
  });

  it('goes connecting → registered and back to reconnecting on a drop', async () => {
    vi.spyOn(tel.telephonyApi, 'webrtcCredentials').mockResolvedValue(CREDS);
    const { engine, fire } = fakeEngine();
    const store = useSoftphoneStore();

    await store.start(() => engine);
    expect(store.state).toBe('connecting');
    expect(engine.connect).toHaveBeenCalledWith(CREDS, expect.any(Function));

    fire({ type: 'registered' });
    expect(store.state).toBe('registered');

    fire({ type: 'disconnected' });
    expect(store.state).toBe('reconnecting');

    fire({ type: 'registered' });
    expect(store.state).toBe('registered');
  });

  it('surfaces a registration failure with its cause', async () => {
    vi.spyOn(tel.telephonyApi, 'webrtcCredentials').mockResolvedValue(CREDS);
    const { engine, fire } = fakeEngine();
    const store = useSoftphoneStore();
    await store.start(() => engine);

    fire({ type: 'registrationFailed', cause: '401 Unauthorized' });
    expect(store.state).toBe('failed');
    expect(store.error).toBe('401 Unauthorized');
  });

  it('tracks a live call and mute, and a denied mic', async () => {
    vi.spyOn(tel.telephonyApi, 'webrtcCredentials').mockResolvedValue(CREDS);
    const { engine, fire } = fakeEngine();
    const store = useSoftphoneStore();
    await store.start(() => engine);
    fire({ type: 'registered' });

    fire({ type: 'callStarted' });
    expect(store.onCall).toBe(true);

    store.toggleMute();
    expect(store.muted).toBe(true);
    expect(engine.setMuted).toHaveBeenCalledWith(true);
    store.toggleMute();
    expect(engine.setMuted).toHaveBeenLastCalledWith(false);

    fire({ type: 'callEnded' });
    expect(store.onCall).toBe(false);
    expect(store.muted).toBe(false); // reset with the call

    fire({ type: 'micDenied' });
    expect(store.micDenied).toBe(true);
    expect(store.statusKey).toBe('micDenied');
  });

  it('stop() disconnects the engine and resets', async () => {
    vi.spyOn(tel.telephonyApi, 'webrtcCredentials').mockResolvedValue(CREDS);
    const { engine, fire } = fakeEngine();
    const store = useSoftphoneStore();
    await store.start(() => engine);
    fire({ type: 'registered' });

    store.stop();
    expect(engine.disconnect).toHaveBeenCalled();
    expect(store.state).toBe('off');
  });

  it('a non-404 credentials error is a failure, not silent', async () => {
    vi.spyOn(tel.telephonyApi, 'webrtcCredentials').mockRejectedValue(
      new ApiError(500, { code: 'server_error', message: 'boom' }),
    );
    const store = useSoftphoneStore();
    await store.start(() => fakeEngine().engine);
    expect(store.state).toBe('failed');
    expect(store.error).toContain('boom');
  });
});
