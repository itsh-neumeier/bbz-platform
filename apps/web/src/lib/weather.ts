import { api } from '@/lib/apiClient';

export interface WeatherHealth {
  overall: 'ok' | 'degraded' | 'stale' | 'down';
  checked_at: string;
  kinds: { kind: string; state: string }[];
}

export interface WeatherAlert {
  id: string;
  region: string;
  type: string;
  level: number;
  valid_from: string | null;
  valid_to: string | null;
  headline: string;
  description: string | null;
  source_ref: string | null;
  received_at: string;
}

export interface WeatherObservation {
  place: string;
  metric: string;
  value: number | null;
  unit: string | null;
  observed_at: string;
  station_ref: string | null;
}

export interface RadarFrame {
  frame_time: string;
  image_ref: string;
}

interface Envelope {
  attribution: string;
  health: WeatherHealth;
}

export const weatherApi = {
  alerts: (signal?: AbortSignal) =>
    api.get<Envelope & { alerts: WeatherAlert[] }>('/weather/alerts', { signal }),
  observations: (signal?: AbortSignal) =>
    api.get<Envelope & { observations: WeatherObservation[] }>('/weather/observations', { signal }),
  radar: (signal?: AbortSignal) =>
    api.get<Envelope & { area: string; frames: RadarFrame[] }>('/weather/radar', { signal }),
  createEvent: (alertId: string) =>
    api.post<{ id: string }>(`/weather/alerts/${alertId}/create-event`),
};
