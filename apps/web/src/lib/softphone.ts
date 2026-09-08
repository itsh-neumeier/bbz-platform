/**
 * WebRTC operator softphone — the JsSIP glue (E13-11 / #816, ADR-0035).
 *
 * BBZ's Asterisk holds a per-operator WebRTC SIP endpoint; the browser
 * registers to it over WSS and, when BBZ bridges a call, Asterisk sends the
 * browser an INVITE which we auto-answer with the microphone (the operator
 * already "answered" in the BBZ UI — this INVITE is only the media path).
 *
 * The state machine lives in `stores/softphone.ts`; this module is the
 * side-effecting engine behind a small interface so the store is unit-testable
 * with a fake. `jssip` is imported lazily so a jsdom test that never calls
 * `connect()` does not pull it in.
 */
import type { WebrtcCredentials } from '@/lib/telephony';

export type SoftphoneEvent =
  | { type: 'registered' }
  | { type: 'unregistered' }
  | { type: 'registrationFailed'; cause: string }
  | { type: 'disconnected' }
  | { type: 'callStarted' }
  | { type: 'callEnded' }
  | { type: 'micDenied' };

export interface SoftphoneEngine {
  /** Register the UA and start listening for BBZ's media INVITEs. */
  connect(creds: WebrtcCredentials, onEvent: (e: SoftphoneEvent) => void): Promise<void>;
  /** Mute / unmute the operator's microphone on the live call, if any. */
  setMuted(muted: boolean): void;
  /** Tear the UA + any media element down. Safe to call when not connected. */
  disconnect(): void;
}

/** True only when the browser can actually do WebRTC audio (not jsdom, not an
 *  insecure context without `mediaDevices`). */
export function webRtcAudioAvailable(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    typeof navigator.mediaDevices?.getUserMedia === 'function' &&
    typeof RTCPeerConnection !== 'undefined'
  );
}

interface JsSipModule {
  default: {
    WebSocketInterface: new (url: string) => unknown;
    UA: new (config: Record<string, unknown>) => JsSipUA;
    debug: { disable: () => void };
  };
}
interface JsSipUA {
  on(event: string, cb: (data: unknown) => void): void;
  start(): void;
  stop(): void;
}
interface JsSipSession {
  direction: 'incoming' | 'outgoing';
  connection: RTCPeerConnection;
  on(event: string, cb: (data: unknown) => void): void;
  answer(opts: Record<string, unknown>): void;
  terminate(): void;
  mute(opts: { audio: boolean }): void;
  unmute(opts: { audio: boolean }): void;
}

/** The real JsSIP-backed engine. */
export function createJsSipEngine(): SoftphoneEngine {
  let ua: JsSipUA | null = null;
  let session: JsSipSession | null = null;
  let audioEl: HTMLAudioElement | null = null;

  function remoteAudio(): HTMLAudioElement {
    if (!audioEl) {
      audioEl = document.createElement('audio');
      audioEl.autoplay = true;
      audioEl.dataset.bbz = 'softphone-remote';
      document.body.appendChild(audioEl);
    }
    return audioEl;
  }

  async function onIncoming(
    s: JsSipSession,
    creds: WebrtcCredentials,
    onEvent: (e: SoftphoneEvent) => void,
  ): Promise<void> {
    session = s;
    s.on('ended', () => {
      session = null;
      onEvent({ type: 'callEnded' });
    });
    s.on('failed', () => {
      session = null;
      onEvent({ type: 'callEnded' });
    });
    s.on('confirmed', () => onEvent({ type: 'callStarted' }));
    s.connection?.addEventListener('track', (ev) => {
      const [stream] = (ev as RTCTrackEvent).streams;
      if (stream) remoteAudio().srcObject = stream;
    });

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    } catch {
      onEvent({ type: 'micDenied' });
      s.terminate();
      session = null;
      return;
    }
    s.answer({
      mediaStream: stream,
      pcConfig: { iceServers: creds.ice_servers },
      mediaConstraints: { audio: true, video: false },
    });
  }

  return {
    async connect(creds, onEvent) {
      const JsSIP = ((await import('jssip')) as unknown as JsSipModule).default;
      JsSIP.debug.disable();
      const socket = new JsSIP.WebSocketInterface(creds.ws_url);
      ua = new JsSIP.UA({
        sockets: [socket],
        uri: creds.sip_uri,
        password: creds.auth_password,
        register: true,
        session_timers: false,
        user_agent: 'BBZ-Softphone',
      });
      ua.on('registered', () => onEvent({ type: 'registered' }));
      ua.on('unregistered', () => onEvent({ type: 'unregistered' }));
      ua.on('registrationFailed', (d) =>
        onEvent({ type: 'registrationFailed', cause: causeOf(d) }),
      );
      ua.on('disconnected', () => onEvent({ type: 'disconnected' }));
      ua.on('newRTCSession', (d) => {
        const s = (d as { session: JsSipSession }).session;
        if (s.direction === 'incoming') void onIncoming(s, creds, onEvent);
      });
      ua.start();
    },
    setMuted(muted) {
      if (!session) return;
      if (muted) session.mute({ audio: true });
      else session.unmute({ audio: true });
    },
    disconnect() {
      try {
        session?.terminate();
      } catch {
        /* already gone */
      }
      try {
        ua?.stop();
      } catch {
        /* already gone */
      }
      session = null;
      ua = null;
      if (audioEl) {
        audioEl.srcObject = null;
        audioEl.remove();
        audioEl = null;
      }
    },
  };
}

function causeOf(d: unknown): string {
  const c = (d as { cause?: unknown } | null)?.cause;
  return typeof c === 'string' && c ? c : 'Registrierung fehlgeschlagen';
}
