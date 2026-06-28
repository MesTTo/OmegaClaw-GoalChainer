import {useCurrentFrame, useVideoConfig} from 'remotion';
import {c, fonts} from '../theme';
import {Stage, Node, Arrow, Caption, Kicker, Centered, rise, fade} from './Parts';

// The new pedagogical scenes. Each walks one idea, revealed step by step with
// arrows, in plain language, using the project's real content and exact figures.

// ── Hook ── lead with the stakes and the headline (it now runs in TypeScript).
export const Hook: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return (
    <Centered>
      <div style={{textAlign: 'center', maxWidth: 1400}}>
        <Kicker color={c.teal} opacity={rise(frame, fps, 0)} mb={26}>OmegaClaw · BGI Sprint</Kicker>
        <div style={{fontFamily: fonts.serif, fontWeight: 600, fontSize: 84, lineHeight: '92px', color: c.serif, opacity: rise(frame, fps, 6), transform: `translateY(${(1 - rise(frame, fps, 6)) * 16}px)`}}>
          GoalChainer
        </div>
        <div style={{fontFamily: fonts.sans, fontSize: 30, lineHeight: '42px', color: c.text, marginTop: 28, opacity: rise(frame, fps, 16)}}>
          An agent could fix the outage by leaking customer data.
          <br />
          Watch it reason its way to the safe call instead.
        </div>
        <div style={{fontFamily: fonts.mono, fontSize: 19, color: c.dim, marginTop: 30, opacity: rise(frame, fps, 28)}}>
          a goal-aware decision layer · running in pure TypeScript on{' '}
          <span style={{color: c.teal}}>MeTTa-TS</span>, and on PeTTa
        </div>
      </div>
    </Centered>
  );
};

// ── Problem ── the incident, framed as the conflict.
export const Problem: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Stage kicker="the problem" kickerColor={c.amber}
      title={<>A service is down. Engineers want to paste the raw logs into the public channel — they carry <span style={{color: c.red}}>customer emails, order IDs, access tokens</span>.</>}>
      <div style={{fontFamily: fonts.sans, fontSize: 26, lineHeight: '38px', color: c.dim, maxWidth: 1300, opacity: fade(frame, 22)}}>
        Sharing everything helps the team fix it fast. It also exposes people, and breaks a norm.
        The agent has to weigh <span style={{color: c.collective}}>the collective goal</span>,{' '}
        <span style={{color: c.individual}}>the individual goal</span>, and the rules — before it acts.
      </div>
    </Stage>
  );
};

// ── The causal chain ── the spine: one step caused by the last, with arrows.
const CHAIN: {tag: string; label: string; accent: string; caption: React.ReactNode}[] = [
  {tag: 'input', label: 'natural-language request', accent: c.dim, caption: 'A person asks in plain English. Messy, ambiguous, urgent.'},
  {tag: 'translate', label: 'structured-English propositions', accent: c.teal, caption: 'It is rewritten into clear claims: one subject, one predicate, one object per line.'},
  {tag: 'ground', label: 'MeTTa atoms (Semantic-Hypergraph)', accent: c.teal, caption: 'Each claim becomes a HyperBase atom the reasoning engines can act on.'},
  {tag: 'reason', label: 'deontic · PLN · SNARS · MetaMo', accent: c.amber, caption: 'Four engines reason over it: the norms, the graded belief, a subjective-logic opinion, and the clash of goals.'},
  {tag: 'verdict', label: 'ranked verdict, with a proof', accent: c.red, caption: 'Each action comes back forbidden / obligated / permitted, with a score and a proof chain.'},
  {tag: 'act', label: 'executed, then leak-checked', accent: c.green, caption: 'The chosen action runs on the real data, and a check confirms no secret survived.'},
];

export const CausalChain: React.FC = () => {
  const frame = useCurrentFrame();
  const step = 30; // frames between reveals
  const focus = Math.min(CHAIN.length - 1, Math.floor(frame / step));
  return (
    <Stage kicker="how it decides" title="One causal chain, start to finish.">
      <div style={{display: 'flex', gap: 64, height: '100%'}}>
        <div style={{display: 'flex', flexDirection: 'column', gap: 0, width: 470}}>
          {CHAIN.map((n, i) => {
            const shown = fade(frame, i * step, 12);
            const arrowShown = fade(frame, i * step - 6, 14);
            return (
              <div key={n.tag}>
                {i > 0 ? (
                  <div style={{position: 'relative', height: 30, marginLeft: 30}}>
                    <Arrow shown={arrowShown} length={30} vertical accent={n.accent} style={{top: 0, left: 0}} />
                  </div>
                ) : null}
                <Node tag={n.tag} label={n.label} accent={n.accent} width={460} shown={shown} />
              </div>
            );
          })}
        </div>
        <div style={{flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center'}}>
          <div style={{fontFamily: fonts.mono, fontSize: 14, letterSpacing: 2, textTransform: 'uppercase', color: CHAIN[focus]!.accent, marginBottom: 16}}>
            {`step ${focus + 1} / ${CHAIN.length} · ${CHAIN[focus]!.tag}`}
          </div>
          <div style={{fontFamily: fonts.serif, fontSize: 40, lineHeight: '52px', color: c.serif, marginBottom: 22}}>
            {CHAIN[focus]!.label}
          </div>
          <Caption shown={1} accent={CHAIN[focus]!.accent}>{CHAIN[focus]!.caption}</Caption>
        </div>
      </div>
    </Stage>
  );
};

// ── Translation ── real English -> real propositions -> real MeTTa atoms.
const PROPS = [
  'Raw incident logs contain customer emails.',
  'Publishing raw incident logs exposes identifiable user data.',
  'The redacted summary protects privacy.',
];
const ATOMS = [
  '(given (risky publish_raw_log))',
  '(hb edge incident-pii-1',
  '   (contains/Pv.so raw_incident_logs/Cc customer_emails/Cc))',
  '(hb source incident-risk-1',
  '   "Publishing raw incident logs exposes identifiable user data.")',
];

export const Translation: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Stage kicker="from english to atoms" title="How natural text becomes something a machine can reason over.">
      <div style={{display: 'flex', alignItems: 'stretch', gap: 40, height: '100%'}}>
        <div style={{flex: 1, padding: 24, borderRadius: 12, background: c.panel, border: `1px solid ${c.edge}`, opacity: fade(frame, 0), display: 'flex', flexDirection: 'column'}}>
          <div style={{fontFamily: fonts.mono, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color: c.dim}}>the request</div>
          <div style={{fontFamily: fonts.sans, fontSize: 23, lineHeight: '33px', color: c.text, marginTop: 14}}>
            “Engineering wants to paste raw logs into the incident room. The logs may include customer emails, order IDs, and request payloads.”
          </div>
          <div style={{marginTop: 'auto', paddingTop: 20, fontFamily: fonts.mono, fontSize: 14, letterSpacing: 2, textTransform: 'uppercase', color: c.teal, opacity: fade(frame, 30)}}>↓ rewritten as propositions</div>
          <div style={{marginTop: 14}}>
            {PROPS.map((p, i) => (
              <div key={i} style={{fontFamily: fonts.sans, fontSize: 19, color: c.text, padding: '7px 0', opacity: fade(frame, 34 + i * 10)}}>
                <span style={{color: c.teal}}>·</span> {p}
              </div>
            ))}
          </div>
        </div>
        <div style={{width: 70, position: 'relative'}}>
          <Arrow shown={fade(frame, 70)} length={56} accent={c.teal} style={{top: '50%', left: 6}} />
        </div>
        <div style={{flex: 1, padding: 24, borderRadius: 12, background: '#0a1016', border: `1px solid ${c.teal}`, opacity: fade(frame, 76), display: 'flex', flexDirection: 'column'}}>
          <div style={{fontFamily: fonts.mono, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color: c.teal}}>the MeTTa atoms</div>
          <div style={{marginTop: 16}}>
            {ATOMS.map((a, i) => (
              <div key={i} style={{fontFamily: fonts.mono, fontSize: 18, lineHeight: '28px', color: a.startsWith('   ') ? c.dim : c.text, opacity: fade(frame, 82 + i * 8)}}>{a}</div>
            ))}
          </div>
          <div style={{marginTop: 'auto', paddingTop: 18, fontFamily: fonts.sans, fontSize: 19, color: c.dim, opacity: fade(frame, 128)}}>
            Now the engines can act on it. Same meaning, machine-readable.
          </div>
        </div>
      </div>
    </Stage>
  );
};
