/** jsdom lacks a few browser globals the app touches. */
import { vi } from 'vitest';

if (typeof globalThis.EventSource === 'undefined') {
  class FakeEventSource {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSED = 2;
    url: string;
    readyState = 0;
    withCredentials = false;
    onopen: ((e: Event) => void) | null = null;
    onmessage: ((e: MessageEvent) => void) | null = null;
    onerror: ((e: Event) => void) | null = null;
    constructor(url: string) {
      this.url = url;
    }
    addEventListener = vi.fn();
    removeEventListener = vi.fn();
    close = vi.fn();
  }
  globalThis.EventSource = FakeEventSource as unknown as typeof EventSource;
}

if (typeof HTMLDialogElement !== 'undefined') {
  HTMLDialogElement.prototype.showModal ||= vi.fn();
  HTMLDialogElement.prototype.close ||= vi.fn();
}
