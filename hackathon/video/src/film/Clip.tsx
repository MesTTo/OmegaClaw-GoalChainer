import {OffthreadVideo, staticFile, useCurrentFrame, interpolate, useVideoConfig} from 'remotion';
import {c, fonts} from './theme';
import {AnnotationCard, CalloutBlock, Connector, calloutReveal, type CardNote} from './Card';
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

// One step of the agent loop. The caption shows whichever step is current (the last
// one whose `at` has passed), so a single slot narrates a many-cycle run without
// stacking cards.
export type Step = {at: number; accent: string; tag: string; title: string; body: string};

const STEP_X = 1270;
const STEP_W = 570;
const STEP_TOP = 348;

export const StepCaption: React.FC<{steps: Step[]}> = ({steps}) => {
  const frame = useCurrentFrame();
  let idx = -1;
  for (let i = 0; i < steps.length; i++) if (frame >= steps[i].at) idx = i;
  if (idx < 0) return null;

  const step = steps[idx];
  const op = interpolate(frame - step.at, [0, 12], [0, 1], {extrapolateRight: 'clamp'});
  const cardY = STEP_TOP + 40;
  const anchorY = cardY + 44;
  const path = `M ${PANEL_RIGHT} ${anchorY} C ${PANEL_RIGHT + 20} ${anchorY}, ${STEP_X - 20} ${anchorY}, ${STEP_X} ${anchorY}`;

  return (
    <>
      <div
        style={{
          position: 'absolute',
          left: STEP_X,
          top: STEP_TOP,
          width: STEP_W,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          fontFamily: fonts.mono,
        }}
      >
        <span style={{color: step.accent, fontSize: 14, letterSpacing: 2}}>
          {`STEP 0${idx + 1} / 0${steps.length}`}
        </span>
        <div style={{flex: 1}} />
        {steps.map((s, i) => (
          <div
            key={i}
            style={{
              width: i === idx ? 24 : 9,
              height: 6,
              borderRadius: 3,
              background: i <= idx ? step.accent : c.edge,
              transition: 'all 0.2s',
            }}
          />
        ))}
      </div>
      <Connector d={path} accent={step.accent} draw={1} anchorX={PANEL_RIGHT} anchorY={anchorY} />
      <AnnotationCard
        x={STEP_X}
        y={cardY}
        w={STEP_W}
        accent={step.accent}
        label={step.tag}
        title={step.title}
        body={step.body}
        opacity={op}
      />
    </>
  );
};
