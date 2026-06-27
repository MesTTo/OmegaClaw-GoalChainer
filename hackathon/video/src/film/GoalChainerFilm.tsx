import {AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig, interpolate} from 'remotion';
import {Background} from './Background';
import {Fonts} from './Fonts';
import {Terminal} from './Terminal';
import {Annotation} from './Annotation';
import {Title, Problem, Closing} from './Cards';
import {scenes, type Scene} from './scenes';
import {c, fonts} from './theme';

const TITLE = 90;
const PROBLEM = 135;
const CLOSING = 180;

export const timeline = () => {
  const segs: {from: number; dur: number}[] = [];
  let t = 0;
  const push = (dur: number) => {
    const d = Math.round(dur);
    segs.push({from: t, dur: d});
    t += d;
  };
  push(TITLE);
  push(PROBLEM);
  scenes.forEach((s) => push(s.duration));
  push(CLOSING);
  return {segs, total: t};
};

const SceneView: React.FC<{scene: Scene; index: number}> = ({scene, index}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const o = Math.min(
    interpolate(frame, [0, 12], [0, 1], {extrapolateRight: 'clamp'}),
    interpolate(frame, [durationInFrames - 16, durationInFrames], [1, 0], {extrapolateLeft: 'clamp'}),
  );
  const question = scene.label.split('— ')[1] ?? scene.label;
  return (
    <AbsoluteFill style={{opacity: o}}>
      <div style={{position: 'absolute', left: 96, top: 78}}>
        <span style={{fontFamily: fonts.mono, fontSize: 20, color: c.teal}}>{`0${index + 1}`}</span>
        <span style={{fontFamily: fonts.mono, fontSize: 20, color: c.faint}}>{` / 0${scenes.length}`}</span>
        <div style={{fontFamily: fonts.serif, fontSize: 30, color: c.serif, marginTop: 6}}>{question}</div>
      </div>
      <Terminal label={scene.label} command={scene.command} lines={scene.lines} />
      {scene.notes.map((n, i) => (
        <Annotation key={i} note={n} />
      ))}
    </AbsoluteFill>
  );
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

export const GoalChainerFilm: React.FC = () => {
  const {segs} = timeline();
  return (
    <AbsoluteFill style={{backgroundColor: c.bg}}>
      <Fonts />
      <Background />
      <Sequence from={segs[0].from} durationInFrames={segs[0].dur}>
        <Title />
      </Sequence>
      <Sequence from={segs[1].from} durationInFrames={segs[1].dur}>
        <Problem />
      </Sequence>
      {scenes.map((s, i) => (
        <Sequence key={s.id} from={segs[2 + i].from} durationInFrames={segs[2 + i].dur}>
          <SceneView scene={s} index={i} />
        </Sequence>
      ))}
      <Sequence from={segs[segs.length - 1].from} durationInFrames={segs[segs.length - 1].dur}>
        <Closing />
      </Sequence>
      <Progress />
    </AbsoluteFill>
  );
};
