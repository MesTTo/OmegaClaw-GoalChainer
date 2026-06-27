import {AbsoluteFill, useCurrentFrame, interpolate, spring, useVideoConfig} from 'remotion';
import {c, fonts} from './theme';

const up = (frame: number, fps: number, delay: number) =>
  spring({frame: frame - delay, fps, config: {damping: 200, mass: 0.6}});

export const Title: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center'}}>
      <div style={{textAlign: 'center', maxWidth: 1300}}>
        <div
          style={{
            fontFamily: fonts.mono,
            fontSize: 16,
            letterSpacing: 5,
            textTransform: 'uppercase',
            color: c.teal,
            opacity: up(frame, fps, 0),
            marginBottom: 26,
          }}
        >
          OmegaClaw · BGI Sprint
        </div>
        <div
          style={{
            fontFamily: fonts.serif,
            fontWeight: 600,
            fontSize: 96,
            lineHeight: '96px',
            color: c.serif,
            opacity: up(frame, fps, 6),
            transform: `translateY(${(1 - up(frame, fps, 6)) * 16}px)`,
          }}
        >
          GoalChainer
        </div>
        <div
          style={{
            fontFamily: fonts.sans,
            fontSize: 27,
            color: c.dim,
            marginTop: 24,
            opacity: up(frame, fps, 16),
          }}
        >
          a goal-aware decision layer that reasons about individual and collective
          goals before acting — running on PeTTa
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const Problem: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const o = interpolate(frame, [0, 18], [0, 1], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center'}}>
      <div style={{maxWidth: 1180, opacity: o}}>
        <div
          style={{
            fontFamily: fonts.mono,
            fontSize: 15,
            letterSpacing: 4,
            textTransform: 'uppercase',
            color: c.amber,
            marginBottom: 30,
          }}
        >
          the problem
        </div>
        <div style={{fontFamily: fonts.serif, fontSize: 52, lineHeight: '66px', color: c.serif}}>
          A service is down. Engineers want to share the raw logs — they may carry{' '}
          <span style={{color: c.red}}>customer emails, order IDs, access tokens</span>. What
          should the agent send, and to whom?
        </div>
        <div
          style={{
            fontFamily: fonts.sans,
            fontSize: 24,
            color: c.dim,
            marginTop: 34,
            opacity: up(frame, fps, 24),
          }}
        >
          The agent should weigh whose goal is helped, whose is harmed, which norms forbid it,
          and how strongly each option is believed acceptable — before it acts.
        </div>
      </div>
    </AbsoluteFill>
  );
};

const layers: [string, string][] = [
  ['perception', 'HyperBase SH parse + Ollama embeddings'],
  ['norms', 'lib_deontic — defeasible + deontic logic'],
  ['belief', 'PeTTaChainer — PLN, with a proof'],
  ['deduction', 'SNARS — Subjective-Logic NARS + provenance'],
  ['motivation', 'MetaMo — individual vs collective consensus'],
  ['coordination', 'lib_directive — a claimable task'],
  ['decision', 'gc_score.pl — the verdict, in Prolog'],
];

export const Closing: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center'}}>
      <div style={{width: 1180}}>
        <div
          style={{
            fontFamily: fonts.mono,
            fontSize: 15,
            letterSpacing: 4,
            textTransform: 'uppercase',
            color: c.teal,
            marginBottom: 22,
            opacity: up(frame, fps, 0),
          }}
        >
          one decision · seven real systems · one runtime
        </div>
        {layers.map(([k, v], i) => {
          const o = up(frame, fps, 6 + i * 5);
          return (
            <div
              key={k}
              style={{
                display: 'flex',
                alignItems: 'baseline',
                gap: 22,
                padding: '11px 0',
                borderBottom: `1px solid ${c.edge}`,
                opacity: o,
                transform: `translateX(${(1 - o) * 16}px)`,
              }}
            >
              <div style={{fontFamily: fonts.mono, fontSize: 15, color: c.dim, width: 150, letterSpacing: 1}}>
                {k}
              </div>
              <div style={{fontFamily: fonts.sans, fontSize: 24, color: c.text}}>{v}</div>
            </div>
          );
        })}
        <div
          style={{
            fontFamily: fonts.serif,
            fontWeight: 600,
            fontSize: 38,
            color: c.serif,
            marginTop: 34,
            opacity: up(frame, fps, 6 + layers.length * 5 + 6),
          }}
        >
          Real reasoning. <span style={{color: c.teal}}>Input-driven.</span>{' '}
          <span style={{color: c.green}}>Verified.</span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
