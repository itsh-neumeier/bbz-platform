import { api } from '@/lib/apiClient';
import type { EventPriority } from '@/lib/events';

/** DWD refresh health per data kind (E18-06). Mirrors `weather.py::KindHealthOut`. */
export interface WeatherKindHealth {
  data_kind: string;
  status: 'ok' | 'stale' | 'degraded' | 'down';
  last_success_at: string | null;
  last_error: string | null;
  age_seconds: number | null;
}

export interface WeatherHealth {
  overall: 'ok' | 'degraded' | 'stale' | 'down';
  checked_at: string;
  kinds: WeatherKindHealth[];
}

export interface WeatherAlert {
  id: string;
  region: string;
  type: string;
  /** DWD warn level "1".."4" (1 yellow … 4 violet) — a string by the E18-02 convention. */
  level: string;
  valid_from: string | null;
  valid_to: string | null;
  headline: string | null;
  description: string | null;
  source_ref: string;
  received_at: string;
}

export interface WeatherObservation {
  place: string;
  metric: string;
  value: number | null;
  unit: string;
  observed_at: string;
  station_ref: string;
}

export interface RadarFrame {
  frame_time: string;
  image_ref: string;
}

interface Envelope {
  attribution: string;
  health: WeatherHealth;
}

/** Body for `POST /weather/alerts/{id}/create-event` (E18-08). `priority` is required. */
export interface CreateWeatherEventBody {
  priority: EventPriority;
  /** the operator's operational assessment ("betriebliche Bewertung"). */
  assessment?: string | null;
}

export interface WeatherEventCreated {
  event_id: string;
  weather_alert_id: string;
  source_ref: string;
  priority: EventPriority;
  created: boolean;
}

/** Map a DWD warn level to a sensible default event priority for the create dialog. */
export function suggestPriority(level: string): EventPriority {
  switch (level) {
    case '4':
      return 'critical';
    case '3':
      return 'high';
    case '2':
      return 'medium';
    default:
      return 'low';
  }
}

export const weatherApi = {
  alerts: (signal?: AbortSignal) =>
    api.get<Envelope & { alerts: WeatherAlert[] }>('/weather/alerts', { signal }),
  observations: (signal?: AbortSignal) =>
    api.get<Envelope & { observations: WeatherObservation[] }>('/weather/observations', { signal }),
  radar: (signal?: AbortSignal) =>
    api.get<Envelope & { area: string; frames: RadarFrame[] }>('/weather/radar', { signal }),
  createEvent: (alertId: string, body: CreateWeatherEventBody) =>
    api.post<WeatherEventCreated>(`/weather/alerts/${alertId}/create-event`, body),
};
