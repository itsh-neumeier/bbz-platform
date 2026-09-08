import { defineStore } from 'pinia';
import { ApiError } from '@/lib/apiClient';
import { telephonyApi, type WebrtcCredentials } from '@/lib/telephony';
import {
  createJsSipEngine,
  webRtcAudioAvailable,
  type SoftphoneEngine,
  type SoftphoneEvent,
} from '@/lib/softphone';

/**
 * The WebRTC operator softphone (E13-11 / #816, ADR-0035).
 *
 * `start()` fetches the operator's credentials and registers a JsSIP UA over
 * WSS; when BBZ bridges a call, Asterisk INVITEs the browser and the engine
 * auto-answers with the microphone. This store is the state machine — the
 * JsSIP side-effects live behind {@link SoftphoneEngine} so it is unit-testable.
 *
 * `off` is the resting state for the common case (no softphone endpoint, or a
 * browser that can't do WebRTC) — it must never look like an error.
 */
export type SoftphoneState =
  | 'off' // no endpoint / not started
  | 'unsupported' // this browser can't do WebRTC audio
  | 'connecting'
  | 'registered'
  | 'reconnecting'
  | 'failed';

interface State {
  state: SoftphoneState;
  /** the operator muted their own mic */
  muted: boolean;
  /** getUserMedia was denied — the operator must grant mic access */
  micDenied: boolean;
  /** a JsSIP media session is up (the operator is audibly on a call) */
  onCall: boolean;
  error: string | null;
}

// the engine + its identity are side-effecting singletons, kept out of the
// reactive state (a JsSIP UA is not serialisable and must not be proxied)
let engine: SoftphoneEngine | null = null;

export const useSoftphoneStore = defineStore('softphone', {
  state: (): State => ({
    state: 'off',
    muted: false,
    micDenied: false,
    onCall: false,
    error: null,
  }),
  getters: {
    /** show the softphone status row at all */
    active: (s): boolean => s.state !== 'off',
    /** a short status key for i18n (`comms.softphone.<key>`) */
    statusKey: (s): string => (s.micDenied ? 'micDenied' : s.state),
  },
  actions: {
    /**
     * Fetch credentials + register. Best-effort: a 404 / 503 (no endpoint, or no
     * WSS URL deployed) leaves the softphone `off` silently. `makeEngine` is a
     * test seam.
     */
    async start(makeEngine: () => SoftphoneEngine = createJsSipEngine): Promise<void> {
      if (engine || this.state === 'connecting' || this.state === 'registered') return;

      let creds: WebrtcCredentials;
      try {
        creds = await telephonyApi.webrtcCredentials();
      } catch (e) {
        if (e instanceof ApiError && (e.status === 404 || e.status === 503)) return; // no softphone
        this.state = 'failed';
        this.error = e instanceof Error ? e.message : String(e);
        return;
      }

      if (!webRtcAudioAvailable()) {
        this.state = 'unsupported';
        return;
      }

      this.state = 'connecting';
      this.error = null;
      engine = makeEngine();
      try {
        await engine.connect(creds, (ev) => this._onEvent(ev));
      } catch (e) {
        this.state = 'failed';
        this.error = e instanceof Error ? e.message : String(e);
        engine = null;
      }
    },

    _onEvent(ev: SoftphoneEvent): void {
      switch (ev.type) {
        case 'registered':
          this.state = 'registered';
          this.error = null;
          break;
        case 'unregistered':
        case 'disconnected':
          if (this.state === 'registered') this.state = 'reconnecting';
          break;
        case 'registrationFailed':
          this.state = 'failed';
          this.error = ev.cause;
          break;
        case 'micDenied':
          this.micDenied = true;
          this.onCall = false;
          break;
        case 'callStarted':
          this.onCall = true;
          this.micDenied = false;
          break;
        case 'callEnded':
          this.onCall = false;
          this.muted = false;
          break;
      }
    },

    toggleMute(): void {
      this.muted = !this.muted;
      engine?.setMuted(this.muted);
    },

    stop(): void {
      engine?.disconnect();
      engine = null;
      this.$reset();
    },
  },
});
