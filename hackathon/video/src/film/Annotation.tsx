import {useCurrentFrame, interpolate, useVideoConfig} from 'remotion';
import {term, lineY} from './theme';
import {CalloutBlock, calloutReveal, type CardNote} from './Card';

// A line-pointing annotation: the shared card content plus the terminal line index.
export type Note = CardNote & {line: number};

const CARD_X = 1148;
const CARD_W = 690;
const TARGET_X = term.x + term.w - 10;

export const Annotation: React.FC<{note: Note}> = ({note}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (frame < note.at) return null;

  const {p, draw} = calloutReveal(frame, fps, note.at);
  const cardMidY = note.cardY + 52;
  const ty = lineY(note.line);
  // a smooth elbow from the card's left edge to the terminal line
  const path = `M ${CARD_X} ${cardMidY} C ${CARD_X - 90} ${cardMidY}, ${TARGET_X + 110} ${ty}, ${TARGET_X} ${ty}`;
  const arrowOpacity = interpolate(frame, [note.at + 24, note.at + 30], [0, 1], {extrapolateRight: 'clamp'});

  return (
    <CalloutBlock
      note={note}
      cardX={CARD_X}
      cardW={CARD_W}
      p={p}
      connector={{
        d: path,
        accent: note.accent,
        draw,
        anchorX: TARGET_X,
        anchorY: ty,
        arrow: draw > 0.98 ? {x: TARGET_X, y: ty, opacity: arrowOpacity} : undefined,
      }}
    />
  );
};
