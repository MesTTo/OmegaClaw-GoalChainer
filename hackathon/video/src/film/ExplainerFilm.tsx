import {AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig} from 'remotion';
import {Background} from './Background';
import {Fonts} from './Fonts';
import {Terminal} from './Terminal';
import {Annotation} from './Annotation';
import {ClipPanel, SideCallout, type Callout} from './Clip';
import {scenes} from './scenes';
import {c} from './theme';
import {FullBleed} from './explainer/Parts';
import {Hook, Problem, CausalChain, Translation} from './explainer/Scenes';
import {DeonticKeywords, DeonticEthics, Pln, MetaMo, Verdict, MettaTs, Close} from './explainer/Scenes2';

// The redesigned explainer: a pedagogical, causal-arrow walk through the pipeline,
// the deontic and PLN foundations, the goal conflict, the verdict, the real run,
// and the MeTTa-TS headline. Built from the explainer scenes plus the project's
// real solve terminal and a compact clip of the genuine Codex-driven run.

const solve = scenes.find((s) => s.id === 'solve')!;

// The real solve output, with its line-pointing annotations and a kicker.
const SolveScene: React.FC = () => (
  <FullBleed kicker="it actually solves it · real data in, safe artifact out" kickerColor={c.green}>
    <Terminal label={solve.label} command={solve.command ?? ''} lines={solve.lines ?? []} />
    {(solve.notes ?? []).map((n, i) => (
      <Annotation key={i} note={n} />
    ))}
  </FullBleed>
);

const recCallouts: Callout[] = [
  {at: 40, cardY: 250, accent: c.teal, label: 'real run · not a mockup', title: 'Codex drives OmegaClaw Core.', body: 'OpenAI Codex (gpt-5.5, reasoning effort xhigh) is the provider in OmegaClaw’s loop, calling the GoalChainer skill one command per cycle.'},
  {at: 300, cardY: 470, accent: c.green, label: 'six cycles · one answer', title: 'It works the incident end to end.', body: 'SNARS, MetaMo, the ranked decision, then solve: it redacts every secret, leak-checks the output, and sends the safe update.'},
];

// A compact view of the genuine recording, sped up, with two callouts.
const RecordingScene: React.FC = () => (
  <FullBleed kicker="see it run · a real OmegaClaw Core session" kickerColor={c.teal}>
    <ClipPanel src="recordings/codex-omegaclaw-loop.mp4" label="OmegaClaw Core · Codex provider · GoalChainer skill" playbackRate={2.2} />
    {recCallouts.map((n, i) => (
      <SideCallout key={i} note={n} />
    ))}
  </FullBleed>
);

type Seg = {dur: number; el: React.ReactNode};

const SEGMENTS: Seg[] = [
  {dur: 240, el: <Hook />},
  {dur: 180, el: <Problem />},
  {dur: 215, el: <CausalChain />},
  {dur: 175, el: <Translation />},
  {dur: 170, el: <DeonticKeywords />},
  {dur: 150, el: <DeonticEthics />},
  {dur: 190, el: <Pln />},
  {dur: 170, el: <MetaMo />},
  {dur: 155, el: <Verdict />},
  {dur: solve.duration, el: <SolveScene />},
  {dur: 470, el: <RecordingScene />},
  {dur: 185, el: <MettaTs />},
  {dur: 180, el: <Close />},
];

export const explainerTimeline = () => {
  const segs: {from: number; dur: number}[] = [];
  let t = 0;
  for (const s of SEGMENTS) {
    const dur = Math.round(s.dur);
    segs.push({from: t, dur});
    t += dur;
  }
  return {segs, total: t};
};

const Progress: React.FC = () => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const p = frame / durationInFrames;
  return (
    <div style={{position: 'absolute', left: 96, right: 84, bottom: 44, height: 2, background: c.edge}}>
      <div style={{width: `${p * 100}%`, height: '100%', background: c.teal, boxShadow: `0 0 12px ${c.teal}`}} />
    </div>
  );
};

export const ExplainerFilm: React.FC = () => {
  const {segs} = explainerTimeline();
  return (
    <AbsoluteFill style={{backgroundColor: c.bg}}>
      <Fonts />
      <Background />
      {SEGMENTS.map((s, i) => (
        <Sequence key={i} from={segs[i].from} durationInFrames={segs[i].dur}>
          {s.el}
        </Sequence>
      ))}
      <Progress />
    </AbsoluteFill>
  );
};
