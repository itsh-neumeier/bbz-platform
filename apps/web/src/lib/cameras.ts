import { api } from '@/lib/apiClient';

/** One camera the event's CAMERA_OPENED / CAMERA_ACTION_FAILED trail mentions
 *  (E16-12 / ADR-0032). `online` is `null` when the video provider could not be
 *  reached or the camera did not resolve. */
export interface EventCamera {
  ref: string;
  name: string;
  site: string | null;
  online: boolean | null;
  group_ids: string[];
  last_action_state: 'opened' | 'failed';
}

export interface EventCameras {
  /** false when there is no active `video.*` integration — the panel shows
   *  "Video derzeit nicht verfügbar" and still lists the known refs. */
  provider_available: boolean;
  cameras: EventCamera[];
}

export const camerasApi = {
  forEvent: (eventId: string, signal?: AbortSignal) =>
    api.get<EventCameras>(`/events/${eventId}/cameras`, { signal }),

  /** (Re)open one of the event's cameras on a workplace display. Needs the
   *  operator's workplace id — wired once the kiosk provides it (Epic 08). */
  focus: (eventId: string, ref: string, workplaceId: string) =>
    api.post<{ enqueued: boolean; camera_ref: string; workplace_id: string }>(
      `/events/${eventId}/cameras/${encodeURIComponent(ref)}/focus`,
      undefined,
      { workplaceId },
    ),
};
