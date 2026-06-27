import {OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {c} from './theme';
import {CalloutBlock, calloutReveal, type CardNote} from './Card';
import {PanelChrome, HEADER_H} from './Panel';

// A real screen recording shown in the same panel chrome as the reconstructed
// terminals, with callout cards beside it (a connector to the panel edge, no
// per-line arrows since the clip scrolls).

const PANEL = {x: 80, y: 182, w: 1156};
const CONTENT_H = Math.round((PANEL.w * 9) / 16);
const PANEL_RIGHT = PANEL.x + PANEL.w;
const CARD_X = 1270;
const CARD_W = 570;

export type Callout = CardNote;

export const ClipPanel: React.FC<{src: string; label: string; playbackRate?: number}> = ({
  src,
  label,
  playbackRate = 1,
}) => {
  return (
    <PanelChrome x={PANEL.x} y={PANEL.y} w={PANEL.w} h={HEADER_H + CONTENT_H} label={label} status="LIVE · codex exec">
      <div style={{width: '100%', height: CONTENT_H, background: c.bg}}>
        <OffthreadVideo
          muted
          src={staticFile(src)}
          playbackRate={playbackRate}
          style={{width: '100%', height: '100%', objectFit: 'cover'}}
        />
      </div>
    </PanelChrome>
  );
};

export const SideCallout: React.FC<{note: Callout}> = ({note}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (frame < note.at) return null;

  const {p, draw} = calloutReveal(frame, fps, note.at);
  const midY = note.cardY + 46;
  // a level run from the panel's right edge to the card
  const path = `M ${PANEL_RIGHT} ${midY} C ${PANEL_RIGHT + 20} ${midY}, ${CARD_X - 20} ${midY}, ${CARD_X} ${midY}`;

  return (
    <CalloutBlock
      note={note}
      cardX={CARD_X}
      cardW={CARD_W}
      p={p}
      connector={{d: path, accent: note.accent, draw, anchorX: PANEL_RIGHT, anchorY: midY}}
    />
  );
};
