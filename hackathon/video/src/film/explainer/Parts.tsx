import {AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring} from 'remotion';
import type {CSSProperties} from 'react';
import {c, fonts} from '../theme';

// Shared explainer primitives: scene chrome, an animated causal arrow, a
// term/definition node, and reveal helpers. Every explainer scene draws from
// these so the visual language is one vocabulary and nothing repeats.

/** A spring that rises 0->1 after `delay` frames. */
export const rise = (frame: number, fps: number, delay = 0): number =>
  spring({frame: frame - delay, fps, config: {damping: 200, mass: 0.6}});

/** A clamped linear fade-in after `delay` frames over `span` frames. */
export const fade = (frame: number, delay = 0, span = 14): number =>
  interpolate(frame, [delay, delay + span], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

/** Scene fade-in/out envelope for the whole stage (and reused scenes). */
export const envelope = (frame: number, total: number): number =>
  Math.min(
    interpolate(frame, [0, 14], [0, 1], {extrapolateRight: 'clamp'}),
    interpolate(frame, [total - 16, total], [1, 0], {extrapolateLeft: 'clamp'}),
  );

/** The mono, spaced, uppercase kicker line every scene opens with. */
export const Kicker: React.FC<{color?: string; opacity?: number; mb?: number; children: React.ReactNode}> = ({
  color = c.teal,
  opacity = 1,
  mb = 0,
  children,
}) => (
  <div style={{fontFamily: fonts.mono, fontSize: 16, letterSpacing: 5, textTransform: 'uppercase', color, opacity, marginBottom: mb}}>
    {children}
  </div>
);

/** A kicker pinned to the top-left, for full-bleed terminal / clip scenes. */
export const SceneKicker: React.FC<{color: string; children: React.ReactNode}> = ({color, children}) => (
  <div style={{position: 'absolute', left: 96, top: 92, fontFamily: fonts.mono, fontSize: 16, letterSpacing: 5, textTransform: 'uppercase', color}}>
    {children}
  </div>
);

/** A full-bleed scene (a recording or terminal) with the scene fade and a top kicker. */
export const FullBleed: React.FC<{kicker: string; kickerColor: string; children: React.ReactNode}> = ({
  kicker,
  kickerColor,
  children,
}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  return (
    <AbsoluteFill style={{opacity: envelope(frame, durationInFrames)}}>
      <SceneKicker color={kickerColor}>{kicker}</SceneKicker>
      {children}
    </AbsoluteFill>
  );
};

/** A vertically and horizontally centered scene, for the hook and the close. */
export const Centered: React.FC<{children: React.ReactNode}> = ({children}) => (
  <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center'}}>{children}</AbsoluteFill>
);

/** Scene chrome: a kicker line, a serif headline, and the body content. */
export const Stage: React.FC<{
  kicker: string;
  kickerColor?: string;
  title?: React.ReactNode;
  children: React.ReactNode;
}> = ({kicker, kickerColor = c.teal, title, children}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  return (
    <AbsoluteFill style={{opacity: envelope(frame, durationInFrames), padding: '92px 110px'}}>
      <Kicker color={kickerColor} opacity={fade(frame, 0)}>{kicker}</Kicker>
      {title ? (
        <div
          style={{
            fontFamily: fonts.serif,
            fontSize: 46,
            lineHeight: '58px',
            color: c.serif,
            marginTop: 18,
            maxWidth: 1500,
            opacity: fade(frame, 6),
          }}
        >
          {title}
        </div>
      ) : null}
      <div style={{flex: 1, marginTop: title ? 40 : 30, position: 'relative'}}>{children}</div>
    </AbsoluteFill>
  );
};

/** A boxed node in a causal chain: a small tag over a label, in an accent color. */
export const Node: React.FC<{
  tag: string;
  label: React.ReactNode;
  accent: string;
  width?: number;
  shown: number; // 0..1
  style?: CSSProperties;
}> = ({tag, label, accent, width = 300, shown, style}) => (
  <div
    style={{
      width,
      padding: '18px 22px',
      borderRadius: 12,
      background: c.panel,
      border: `1px solid ${accent}`,
      boxShadow: `0 0 0 1px ${accent}22, 0 18px 40px rgba(0,0,0,0.35)`,
      opacity: shown,
      transform: `translateY(${(1 - shown) * 14}px)`,
      ...style,
    }}
  >
    <div style={{fontFamily: fonts.mono, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color: accent}}>
      {tag}
    </div>
    <div style={{fontFamily: fonts.sans, fontSize: 21, color: c.text, marginTop: 8, lineHeight: '27px'}}>{label}</div>
  </div>
);

/** A causal arrow that draws itself left-to-right (or down) as `shown` goes 0->1. */
export const Arrow: React.FC<{
  shown: number;
  length: number;
  vertical?: boolean;
  accent?: string;
  style?: CSSProperties;
}> = ({shown, length, vertical = false, accent = c.teal, style}) => {
  const drawn = Math.max(0, Math.min(1, shown));
  const head = drawn > 0.85;
  return (
    <div style={{position: 'absolute', ...style}}>
      <div
        style={{
          position: 'absolute',
          background: accent,
          boxShadow: `0 0 10px ${accent}`,
          ...(vertical
            ? {width: 2, height: length * drawn, left: -1}
            : {height: 2, width: length * drawn, top: -1}),
        }}
      />
      <div
        style={{
          position: 'absolute',
          width: 0,
          height: 0,
          opacity: head ? 1 : 0,
          ...(vertical
            ? {
                top: length - 9,
                left: -6,
                borderLeft: '6px solid transparent',
                borderRight: '6px solid transparent',
                borderTop: `9px solid ${accent}`,
              }
            : {
                left: length - 9,
                top: -6,
                borderTop: '6px solid transparent',
                borderBottom: '6px solid transparent',
                borderLeft: `9px solid ${accent}`,
              }),
        }}
      />
    </div>
  );
};

/** A caption line that explains the step currently in focus. */
export const Caption: React.FC<{shown: number; accent: string; children: React.ReactNode}> = ({
  shown,
  accent,
  children,
}) => (
  <div
    style={{
      fontFamily: fonts.sans,
      fontSize: 23,
      lineHeight: '32px',
      color: c.dim,
      opacity: shown,
      transform: `translateY(${(1 - shown) * 8}px)`,
      borderLeft: `2px solid ${accent}`,
      paddingLeft: 18,
    }}
  >
    {children}
  </div>
);
