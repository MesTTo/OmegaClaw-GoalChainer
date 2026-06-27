import {useCurrentFrame, interpolate, spring, useVideoConfig} from 'remotion';
import {c, fonts, term, lineY} from './theme';

export type Note = {
  at: number; // local frame when it appears
  line: number; // terminal line index to point at
  cardY: number; // top of the card
  label: string;
  title: string;
  body: string;
  accent: string;
};

const CARD_X = 1148;
const CARD_W = 690;
const TARGET_X = term.x + term.w - 10;

export const Annotation: React.FC<{note: Note}> = ({note}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (frame < note.at) return null;

  const p = spring({frame: frame - note.at, fps, config: {damping: 200, mass: 0.7}});
  const draw = interpolate(frame, [note.at + 6, note.at + 26], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const cardMidY = note.cardY + 52;
  const ty = lineY(note.line);
  // a smooth elbow from the card's left edge to the terminal line
  const path = `M ${CARD_X} ${cardMidY} C ${CARD_X - 90} ${cardMidY}, ${TARGET_X + 110} ${ty}, ${TARGET_X} ${ty}`;

  return (
    <>
      <svg style={{position: 'absolute', inset: 0}} width={1920} height={1080}>
        <path
          d={path}
          fill="none"
          stroke={note.accent}
          strokeWidth={2.5}
          pathLength={1}
          strokeDasharray={1}
          strokeDashoffset={1 - draw}
          opacity={0.95}
        />
        {draw > 0.98 ? (
          <g
            transform={`translate(${TARGET_X} ${ty})`}
            opacity={interpolate(frame, [note.at + 24, note.at + 30], [0, 1], {extrapolateRight: 'clamp'})}
          >
            <path d="M 0 0 L 16 -6 L 12 0 L 16 6 Z" fill={note.accent} />
          </g>
        ) : null}
        <circle cx={TARGET_X} cy={ty} r={4.5 * draw} fill={note.accent} />
      </svg>

      <div
        style={{
          position: 'absolute',
          left: CARD_X,
          top: note.cardY,
          width: CARD_W,
          opacity: p,
          transform: `translateX(${(1 - p) * 22}px)`,
          background: `linear-gradient(180deg, ${c.panelTop}, ${c.panel})`,
          borderRadius: 12,
          borderLeft: `3px solid ${note.accent}`,
          border: `1px solid ${c.edge}`,
          borderLeftWidth: 3,
          borderLeftColor: note.accent,
          boxShadow: '0 30px 90px rgba(0,0,0,0.5)',
          padding: '22px 26px 24px',
        }}
      >
        <div
          style={{
            fontFamily: fonts.mono,
            fontSize: 13,
            letterSpacing: 2,
            textTransform: 'uppercase',
            color: note.accent,
            marginBottom: 12,
          }}
        >
          {note.label}
        </div>
        <div
          style={{
            fontFamily: fonts.serif,
            fontWeight: 600,
            fontSize: 31,
            lineHeight: '36px',
            color: c.serif,
            marginBottom: 12,
          }}
        >
          {note.title}
        </div>
        <div style={{fontFamily: fonts.sans, fontSize: 20, lineHeight: '29px', color: c.dim}}>
          {note.body}
        </div>
      </div>
    </>
  );
};
