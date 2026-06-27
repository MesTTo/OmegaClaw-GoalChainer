import type {ComponentProps} from 'react';
import {spring, interpolate} from 'remotion';
import {c, fonts} from './theme';

// The editorial card (mono label, serif title, sans body) and the connector that
// links it to the terminal, shared by the line-pointing Annotation and the
// clip-scene SideCallout.

// The content every callout carries; Annotation's Note adds a terminal line to
// point at, the clip's Callout uses it as-is.
export type CardNote = {
  at: number;
  cardY: number;
  accent: string;
  label: string;
  title: string;
  body: string;
};

// Shared reveal timing: the card springs in, the connector draws on.
export const calloutReveal = (frame: number, fps: number, at: number) => ({
  p: spring({frame: frame - at, fps, config: {damping: 200, mass: 0.7}}),
  draw: interpolate(frame, [at + 5, at + 23], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}),
});

export const AnnotationCard: React.FC<{
  x: number;
  y: number;
  w: number;
  accent: string;
  label: string;
  title: string;
  body: string;
  opacity: number;
}> = ({x, y, w, accent, label, title, body, opacity}) => (
  <div
    style={{
      position: 'absolute',
      left: x,
      top: y,
      width: w,
      opacity,
      transform: `translateX(${(1 - opacity) * 22}px)`,
      background: `linear-gradient(180deg, ${c.panelTop}, ${c.panel})`,
      borderRadius: 12,
      border: `1px solid ${c.edge}`,
      borderLeft: `3px solid ${accent}`,
      boxShadow: '0 30px 90px rgba(0,0,0,0.5)',
      padding: '21px 25px 23px',
    }}
  >
    <div
      style={{
        fontFamily: fonts.mono,
        fontSize: 13,
        letterSpacing: 2,
        textTransform: 'uppercase',
        color: accent,
        marginBottom: 11,
      }}
    >
      {label}
    </div>
    <div
      style={{
        fontFamily: fonts.serif,
        fontWeight: 600,
        fontSize: 30,
        lineHeight: '35px',
        color: c.serif,
        marginBottom: 11,
      }}
    >
      {title}
    </div>
    <div style={{fontFamily: fonts.sans, fontSize: 19, lineHeight: '28px', color: c.dim}}>{body}</div>
  </div>
);

export const Connector: React.FC<{
  d: string;
  accent: string;
  draw: number;
  anchorX: number;
  anchorY: number;
  arrow?: {x: number; y: number; opacity: number};
}> = ({d, accent, draw, anchorX, anchorY, arrow}) => (
  <svg style={{position: 'absolute', inset: 0}} width={1920} height={1080}>
    <path
      d={d}
      fill="none"
      stroke={accent}
      strokeWidth={2.5}
      pathLength={1}
      strokeDasharray={1}
      strokeDashoffset={1 - draw}
      opacity={0.92}
    />
    {arrow ? (
      <g transform={`translate(${arrow.x} ${arrow.y})`} opacity={arrow.opacity}>
        <path d="M 0 0 L 16 -6 L 12 0 L 16 6 Z" fill={accent} />
      </g>
    ) : null}
    <circle cx={anchorX} cy={anchorY} r={4.5 * draw} fill={accent} />
  </svg>
);

// A connector plus its card, the shape both Annotation and SideCallout render. The
// caller supplies the connector geometry (an elbow to a line, or a level run to a
// panel edge); the card position and content come from the note.
export const CalloutBlock: React.FC<{
  note: CardNote;
  cardX: number;
  cardW: number;
  p: number;
  connector: ComponentProps<typeof Connector>;
}> = ({note, cardX, cardW, p, connector}) => (
  <>
    <Connector {...connector} />
    <AnnotationCard
      x={cardX}
      y={note.cardY}
      w={cardW}
      accent={note.accent}
      label={note.label}
      title={note.title}
      body={note.body}
      opacity={p}
    />
  </>
);
