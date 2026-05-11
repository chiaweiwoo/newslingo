/**
 * Per-channel display metadata.
 * Add a new entry here whenever a new source is wired up in the scrapers.
 *
 * Colors are pulled from each outlet's actual brand palette so they carry
 * editorial meaning at a glance — red = Zaobao (print newspaper), teal = Astro (TV/digital).
 */
export interface ChannelMeta {
  color: string;   // CSS color for the source label
}

export const CHANNEL_META: Record<string, ChannelMeta> = {
  '联合早报':     { color: '#D42027' },   // Zaobao brand red
  'Astro 本地圈': { color: '#00A3A3' },   // Astro brand teal
};

/** Fallback for any channel not yet in the map */
export const DEFAULT_CHANNEL_COLOR = '#999999';
