import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {c, fonts} from '../theme';
import {Stage, Node, Arrow, Kicker, Centered, rise, fade} from './Parts';

// ── Deontic keywords ── define the three words, then fire the rule.
const DEFS: {word: string; accent: string; def: string; ex: string}[] = [
  {word: 'forbidden', accent: c.red, def: 'the agent must not do it', ex: 'publish the raw log with customer PII'},
  {word: 'obligated', accent: c.amber, def: 'the agent must do it', ex: 'publish a safe, redacted status'},
  {word: 'permitted', accent: c.green, def: 'the agent may, but need not', ex: 'hold the update and wait'},
];

export const DeonticKeywords: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Stage kicker="the norms · deontic logic" title="Three words that regulate the agent.">
      <div style={{display: 'flex', flexDirection: 'column', gap: 16}}>
        {DEFS.map((d, i) => {
          const o = fade(frame, i * 22, 14);
          return (
            <div key={d.word} style={{display: 'flex', alignItems: 'baseline', gap: 26, opacity: o, transform: `translateX(${(1 - o) * 14}px)`}}>
              <div style={{fontFamily: fonts.mono, fontSize: 30, fontWeight: 600, color: d.accent, width: 220}}>{d.word}</div>
              <div style={{fontFamily: fonts.sans, fontSize: 25, color: c.text, width: 430}}>{d.def}</div>
              <div style={{fontFamily: fonts.sans, fontSize: 21, color: c.dim}}>→ {d.ex}</div>
            </div>
          );
        })}
        <div style={{fontFamily: fonts.sans, fontSize: 21, color: c.dim, marginTop: 12, opacity: fade(frame, 72)}}>
          And <span style={{fontFamily: fonts.mono, color: c.teal}}>normally</span>: a defeasible rule. It holds unless a stronger rule overrides it, so the engine can change its mind with new evidence.
        </div>
        <div style={{marginTop: 30, display: 'flex', alignItems: 'center', gap: 18, opacity: fade(frame, 92)}}>
          <Node tag="given" label="(risky publish_raw_log)" accent={c.dim} width={340} shown={fade(frame, 92)} />
          <div style={{position: 'relative', width: 120, height: 2}}>
            <Arrow shown={fade(frame, 104)} length={108} accent={c.red} style={{top: 0, left: 0}} />
            <div style={{position: 'absolute', top: -34, left: 0, width: 120, textAlign: 'center', fontFamily: fonts.mono, fontSize: 14, color: c.red}}>normally</div>
          </div>
          <Node tag="derived" label="(forbidden publish_raw_log)" accent={c.red} width={400} shown={fade(frame, 116)} />
        </div>
      </div>
    </Stage>
  );
};

// ── The ethics argument ── why deontic logic is the elegant way to give an AI ethics.
export const DeonticEthics: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', padding: '0 160px'}}>
      <div style={{maxWidth: 1400}}>
        <Kicker color={c.amber} opacity={rise(frame, fps, 0)} mb={28}>why this matters</Kicker>
        <div style={{fontFamily: fonts.serif, fontSize: 50, lineHeight: '66px', color: c.serif, opacity: rise(frame, fps, 6)}}>
          Deontic logic is the mathematics of <span style={{color: c.amber}}>obligation</span> and <span style={{color: c.green}}>permission</span>.
        </div>
        <div style={{fontFamily: fonts.sans, fontSize: 28, lineHeight: '40px', color: c.dim, marginTop: 30, opacity: rise(frame, fps, 18)}}>
          It may be the most precise, auditable way to give an AI ethics: norms you can read, rules that fire, and a verdict you can prove, not a vibe, not a filter, not a hope.
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ── PLN / Goertzel ── graded belief with strength + confidence.
const DEDS: {label: string; stv: string; accent: string}[] = [
  {label: 'rule: Redacted ⟹ Acceptable', stv: 'STV 0.95 / 0.97', accent: c.teal},
  {label: 'fact: the summary is redacted', stv: 'STV 1.00 / 0.97', accent: c.teal},
];

export const Pln: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Stage kicker="the belief · PLN" title="How strongly should it believe each option?">
      <div style={{fontFamily: fonts.sans, fontSize: 24, lineHeight: '35px', color: c.text, maxWidth: 1400, opacity: fade(frame, 0)}}>
        PeTTaChainer implements <span style={{color: c.teal}}>PLN</span>, Probabilistic Logic Networks, Goertzel, Iklé, Goertzel &amp; Heljakka. Every belief carries two numbers:{' '}
        <span style={{color: c.teal}}>strength</span> (how true) and <span style={{color: c.amber}}>confidence</span> (how settled).
      </div>
      <div style={{display: 'flex', alignItems: 'center', gap: 30, marginTop: 44}}>
        <div style={{display: 'flex', flexDirection: 'column', gap: 14}}>
          {DEDS.map((d, i) => (
            <Node key={i} tag={d.stv} label={d.label} accent={d.accent} width={420} shown={fade(frame, 18 + i * 16)} />
          ))}
        </div>
        <div style={{position: 'relative', width: 110, height: 2}}>
          <Arrow shown={fade(frame, 56)} length={98} accent={c.amber} style={{top: 0, left: 0}} />
          <div style={{position: 'absolute', top: -32, left: 0, width: 110, textAlign: 'center', fontFamily: fonts.mono, fontSize: 14, color: c.amber}}>deduce</div>
        </div>
        <div style={{position: 'relative', width: 110, height: 2}}>
          <Arrow shown={fade(frame, 70)} length={98} accent={c.green} style={{top: 0, left: 0}} />
          <div style={{position: 'absolute', top: -32, left: 0, width: 110, textAlign: 'center', fontFamily: fonts.mono, fontSize: 14, color: c.green}}>revise</div>
        </div>
        <Node tag="(Acceptable redacted)" label={<span style={{fontFamily: fonts.mono}}>STV 0.9339 / 0.9771</span>} accent={c.green} width={360} shown={fade(frame, 84)} />
      </div>
      <div style={{fontFamily: fonts.sans, fontSize: 22, lineHeight: '32px', color: c.dim, marginTop: 40, maxWidth: 1400, opacity: fade(frame, 104)}}>
        Deduction chains beliefs; revision merges evidence. The redacted summary lands at strength 0.93, confidence 0.98, with a proof term. A second engine, <span style={{color: c.amber}}>SNARS</span>, returns the same call as a subjective-logic opinion: belief 0.669, expectation 0.834, with provenance for every premise.
      </div>
    </Stage>
  );
};

// ── MetaMo ── individual vs collective, reconciled by a disagreement penalty.
export const MetaMo: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Stage kicker="the goals · MetaMo" title="Whose goal wins when they collide?">
      <div style={{display: 'flex', gap: 40, marginTop: 10}}>
        <Node tag="the collective" accent={c.collective} width={560} shown={fade(frame, 0)}
          label={<><span style={{color: c.collective}}>Repair and coordinate</span> pull toward the raw log, the most detail. Best: <span style={{fontFamily: fonts.mono}}>publish_raw_log</span>.</>} />
        <Node tag="the individual" accent={c.individual} width={560} shown={fade(frame, 20)}
          label={<><span style={{color: c.individual}}>Privacy</span> pulls the other way. Best: <span style={{fontFamily: fonts.mono}}>publish_redacted_summary</span>.</>} />
      </div>
      <div style={{display: 'flex', justifyContent: 'center', gap: 90, margin: '26px 0 6px'}}>
        <Arrow shown={fade(frame, 44)} length={40} vertical accent={c.collective} style={{position: 'relative', top: 0, left: 0}} />
        <Arrow shown={fade(frame, 48)} length={40} vertical accent={c.individual} style={{position: 'relative', top: 0, left: 0}} />
      </div>
      <div style={{opacity: fade(frame, 60)}}>
        <Node tag="consensus · disagreement-penalized" accent={c.teal} width={1160} shown={fade(frame, 60)}
          label={<>MetaMo scores each action <span style={{fontFamily: fonts.mono, color: c.teal}}>(scoreI + scoreC) / 2 − 0.25 · |scoreI − scoreC|</span>. The action both can accept wins, the <span style={{color: c.green}}>redacted summary</span>. An option one side loves and the other hates is penalized for the gap.</>} />
      </div>
    </Stage>
  );
};

// ── Verdict ── the ranked decision, deontic-gated.
const RANK: {action: string; status: string; score: string; accent: string}[] = [
  {action: 'publish_redacted_summary', status: 'recommended', score: '0.987', accent: c.green},
  {action: 'hold_external_update', status: 'candidate', score: '0.516', accent: c.amber},
  {action: 'publish_raw_log', status: 'blocked', score: '−1.000', accent: c.red},
];

export const Verdict: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Stage kicker="the verdict" title="One ranked decision, gated by the norms.">
      <div style={{display: 'flex', flexDirection: 'column', gap: 18, marginTop: 14}}>
        {RANK.map((r, i) => {
          const o = fade(frame, i * 18, 14);
          return (
            <div key={r.action} style={{display: 'flex', alignItems: 'center', gap: 26, padding: '18px 24px', borderRadius: 12, background: c.panel, border: `1px solid ${r.accent}`, opacity: o, transform: `translateX(${(1 - o) * 16}px)`}}>
              <div style={{fontFamily: fonts.mono, fontSize: 28, color: r.accent, width: 150}}>{r.score}</div>
              <div style={{fontFamily: fonts.mono, fontSize: 15, letterSpacing: 2, textTransform: 'uppercase', color: r.accent, width: 170}}>{r.status}</div>
              <div style={{fontFamily: fonts.sans, fontSize: 26, color: c.text}}>{r.action}</div>
            </div>
          );
        })}
      </div>
      <div style={{fontFamily: fonts.sans, fontSize: 23, lineHeight: '33px', color: c.dim, marginTop: 34, maxWidth: 1400, opacity: fade(frame, 64)}}>
        The forbidden action is forced to <span style={{color: c.red}}>−1.0</span>, and no score can buy it back. The redacted summary, obligated and covering every required goal, is recommended at <span style={{color: c.green}}>0.987</span>.
      </div>
    </Stage>
  );
};

// ── MeTTa-TS ── the headline: the same reasoning, now in pure TypeScript.
export const MettaTs: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Stage kicker="the headline · MeTTa-TS" title="And all of this now runs in pure TypeScript.">
      <div style={{fontFamily: fonts.sans, fontSize: 27, lineHeight: '40px', color: c.text, maxWidth: 1450, opacity: fade(frame, 0)}}>
        The same reasoning, reimplemented on <span style={{color: c.teal}}>MeTTa-TS</span>: a pure-TypeScript MeTTa interpreter. No Prolog, no Python, no native addon. It runs in a browser, an edge function, or inside a TypeScript agent.
      </div>
      <div style={{display: 'flex', gap: 22, marginTop: 40}}>
        {[
          ['differential-tested', 'against the original Python, value-for-value'],
          ['strength 0.9339042316258351', 'the PLN truth value, bit-for-bit'],
          ['score 0.986774', 'the same verdict, the same numbers'],
        ].map(([h, s], i) => (
          <div key={i} style={{flex: 1, padding: 22, borderRadius: 12, background: c.panel, border: `1px solid ${c.teal}`, opacity: fade(frame, 20 + i * 14)}}>
            <div style={{fontFamily: fonts.mono, fontSize: 18, color: c.teal}}>{h}</div>
            <div style={{fontFamily: fonts.sans, fontSize: 20, color: c.dim, marginTop: 10, lineHeight: '28px'}}>{s}</div>
          </div>
        ))}
      </div>
    </Stage>
  );
};

// ── Close ── the standing claim.
export const Close: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return (
    <Centered>
      <div style={{textAlign: 'center'}}>
        <div style={{fontFamily: fonts.serif, fontWeight: 600, fontSize: 64, lineHeight: '74px', color: c.serif, opacity: rise(frame, fps, 0)}}>
          Real reasoning.
          <br />
          <span style={{color: c.teal}}>Input-driven.</span> <span style={{color: c.green}}>Verified.</span> Portable.
        </div>
        <div style={{fontFamily: fonts.mono, fontSize: 19, color: c.dim, marginTop: 34, opacity: rise(frame, fps, 14)}}>
          GoalChainer · OmegaClaw · on PeTTa and MeTTa-TS
        </div>
      </div>
    </Centered>
  );
};
