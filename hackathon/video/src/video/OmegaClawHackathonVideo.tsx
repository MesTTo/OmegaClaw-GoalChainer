import type {CSSProperties, ReactNode} from 'react';
import React from 'react';
import {
  AbsoluteFill,
  Audio,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig
} from 'remotion';
import {auditStats, decisions, hashes, proofSteps} from './data';
import {recordings} from './media.generated';
import {card, fullFrame, palette} from './theme';

const second = (value: number) => Math.round(value * 30);

const scenes = {
  title: {from: 0, duration: second(16)},
  problem: {from: second(16), duration: second(26)},
  codex: {from: second(42), duration: second(34)},
  ranking: {from: second(76), duration: second(38)},
  proof: {from: second(114), duration: second(36)},
  placeholders: {from: second(150), duration: second(20)},
  closing: {from: second(170), duration: second(10)}
};

export const OmegaClawHackathonVideo: React.FC = () => {
  return (
    <AbsoluteFill style={fullFrame}>
      <BackgroundGrid />
      <Sequence from={scenes.title.from} durationInFrames={scenes.title.duration}>
        <TitleScene />
      </Sequence>
      <Sequence from={scenes.problem.from} durationInFrames={scenes.problem.duration}>
        <ProblemScene />
      </Sequence>
      <Sequence from={scenes.codex.from} durationInFrames={scenes.codex.duration}>
        <CodexScene />
      </Sequence>
      <Sequence from={scenes.ranking.from} durationInFrames={scenes.ranking.duration}>
        <RankingScene />
      </Sequence>
      <Sequence from={scenes.proof.from} durationInFrames={scenes.proof.duration}>
        <ProofScene />
      </Sequence>
      <Sequence from={scenes.placeholders.from} durationInFrames={scenes.placeholders.duration}>
        <PlaceholderScene />
      </Sequence>
      <Sequence from={scenes.closing.from} durationInFrames={scenes.closing.duration}>
        <ClosingScene />
      </Sequence>
      {recordings.voiceover ? <Audio src={staticFile(recordings.voiceover)} /> : null}
      <TimeRail />
    </AbsoluteFill>
  );
};

const BackgroundGrid: React.FC = () => {
  return (
    <AbsoluteFill
      style={{
        backgroundImage:
          'linear-gradient(rgba(47, 214, 201, 0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(247, 185, 85, 0.07) 1px, transparent 1px)',
        backgroundSize: '64px 64px',
        opacity: 0.72
      }}
    />
  );
};

const TimeRail: React.FC = () => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const width = `${(frame / durationInFrames) * 100}%`;
  return (
    <div
      style={{
        bottom: 0,
        height: 8,
        left: 0,
        position: 'absolute',
        width,
        background: palette.cyan
      }}
    />
  );
};

const SceneShell: React.FC<{
  eyebrow: string;
  title: string;
  children: ReactNode;
}> = ({eyebrow, title, children}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = spring({fps, frame, config: {damping: 180, stiffness: 120}});
  return (
    <AbsoluteFill
      style={{
        padding: '74px 92px 72px',
        transform: `translateY(${interpolate(enter, [0, 1], [24, 0])}px)`,
        opacity: interpolate(enter, [0, 1], [0, 1])
      }}
    >
      <div style={{color: palette.amber, fontSize: 28, fontWeight: 700, marginBottom: 18}}>
        {eyebrow}
      </div>
      <div style={{fontSize: 64, fontWeight: 800, lineHeight: 1.05, maxWidth: 1320}}>
        {title}
      </div>
      <div style={{marginTop: 42}}>{children}</div>
    </AbsoluteFill>
  );
};

const TitleScene: React.FC = () => {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, 60, 360], [0.94, 1, 1.03], {
    extrapolateRight: 'clamp'
  });
  return (
    <SceneShell eyebrow="BGI Sprint I" title="OmegaClaw GoalChainer">
      <div style={{display: 'grid', gridTemplateColumns: '1.15fr 0.85fr', gap: 42}}>
        <div style={{...card, padding: 46, transform: `scale(${scale})`}}>
          <div style={{fontSize: 42, lineHeight: 1.2, maxWidth: 980}}>
            A decision layer for agents that can rank actions against individual goals,
            collective goals, deontic norms, and proof-backed context.
          </div>
          <div style={{display: 'flex', gap: 18, marginTop: 40}}>
            <Pill color={palette.cyan}>Codex auth</Pill>
            <Pill color={palette.green}>Goal ranking</Pill>
            <Pill color={palette.amber}>PeTTa proof audit</Pill>
          </div>
        </div>
        <StackedSystem />
      </div>
    </SceneShell>
  );
};

const ProblemScene: React.FC = () => {
  return (
    <SceneShell eyebrow="The problem" title="Useful actions can still violate a goal.">
      <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 28}}>
        <SignalCard title="Individual goal" body="Do not expose identifiable user data." accent={palette.rose} />
        <SignalCard title="Collective goal" body="Restore service and coordinate responders." accent={palette.green} />
        <SignalCard title="Norm layer" body="A higher-priority privacy rule blocks raw log sharing." accent={palette.amber} />
      </div>
      <div style={{...card, marginTop: 32, padding: 34, fontSize: 32, color: palette.muted}}>
        The demo uses incident response because the tradeoff is concrete: privacy, repair speed,
        and coordination all matter at the same time.
      </div>
    </SceneShell>
  );
};

const CodexScene: React.FC = () => {
  return (
    <SceneShell eyebrow="Setup friction removed" title="The Codex provider lets OmegaClaw use the logged-in Codex path.">
      <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 30}}>
        {recordings.codexClip ? (
          <ClipOrPlaceholder
            detail="Recorded live provider self-test."
            height={520}
            src={recordings.codexClip}
            title="Live Codex provider self-test"
          />
        ) : (
          <TerminalPanel
            title="Provider self-test"
            lines={[
              '$ python3 lib_codex_auth.py',
              'is_available: True | model: gpt-5.4',
              "reply: 'codex-provider-works'",
              '$ python3 codex_chat.py --selftest',
              "turn1: 'ok'",
              "turn2: '42'",
              'MULTI-TURN MEMORY: PASS'
            ]}
          />
        )}
        <FeatureMatrix
          rows={[
            ['Credential path', '~/.codex/auth.json, values hidden'],
            ['Provider', 'provider=Codex in the OmegaClaw registry'],
            ['Backend', 'Responses API over the Codex subscription route'],
            ['Demo value', 'Less setup before judging the reasoning work']
          ]}
        />
      </div>
    </SceneShell>
  );
};

const RankingScene: React.FC = () => {
  const hasClip = Boolean(recordings.goalchainerClip);
  return (
    <SceneShell eyebrow="Action ranking" title="GoalChainer selects the action that satisfies all required goals.">
      <div style={{display: 'grid', gridTemplateColumns: hasClip ? '0.96fr 1.04fr' : '1fr', gap: 24, alignItems: 'start'}}>
        <div style={{display: 'grid', gridTemplateColumns: '1fr', gap: 22}}>
          {decisions.map((decision, index) => (
            <DecisionRow key={decision.action} decision={decision} index={index} />
          ))}
        </div>
        {recordings.goalchainerClip ? (
          <ClipOrPlaceholder
            detail="Recorded live GoalChainer ranking and PeTTaChainer audit checks."
            height={454}
            src={recordings.goalchainerClip}
            title="Live GoalChainer + PeTTa audit"
          />
        ) : null}
      </div>
    </SceneShell>
  );
};

const ProofScene: React.FC = () => {
  return (
    <SceneShell eyebrow="Proof audit" title="PeTTaChainer turns the decision into a replayable incident proof.">
      <div style={{display: 'grid', gridTemplateColumns: '0.95fr 1.05fr', gap: 30}}>
        <div style={{...card, padding: 32}}>
          <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16}}>
            {auditStats.map((stat) => (
              <Metric key={stat.label} label={stat.label} value={stat.value} />
            ))}
          </div>
          <div style={{marginTop: 28, color: palette.muted, fontSize: 24}}>
            The proof keeps the useful path separate from distractor trust edges and validates the
            bundle by replaying it.
          </div>
        </div>
        <div style={{...card, padding: 32}}>
          {proofSteps.map((step, index) => (
            <ProofLine key={step.label} step={step} index={index} />
          ))}
          <HashLine label="Scenario SHA-256" value={hashes.scenario} />
          <HashLine label="Isolate proof SHA-256" value={hashes.proof} />
        </div>
      </div>
    </SceneShell>
  );
};

const PlaceholderScene: React.FC = () => {
  return (
    <SceneShell eyebrow="Draft assembly" title="Placeholders are ready for the human recordings.">
      <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 34}}>
        <ClipOrPlaceholder
          detail="Suggested clip: live Codex self-test or GoalChainer JSON run."
          src={recordings.codexClip}
          title="Drop in terminal or browser clip"
        />
        <ClipOrPlaceholder
          detail="Optional clip: GoalChainer JSON output or PeTTaChainer proof audit."
          src={recordings.goalchainerClip}
          title="Drop in GoalChainer proof clip"
        />
      </div>
    </SceneShell>
  );
};

const ClosingScene: React.FC = () => {
  const voiceoverLine = recordings.voiceover
    ? 'Voiceover is included. Review the render, upload unlisted, then update Deep Projects.'
    : 'Voiceover is still missing. Record it from voiceover_script.md before upload.';
  return (
    <SceneShell eyebrow="Human handoff" title="Record voiceover, upload unlisted, then update Deep Projects.">
      <div style={{...card, padding: 44, fontSize: 38, lineHeight: 1.25, maxWidth: 1420}}>
        {voiceoverLine}
      </div>
    </SceneShell>
  );
};

const StackedSystem: React.FC = () => {
  return (
    <div style={{...card, padding: 34, display: 'grid', gap: 18}}>
      {[
        ['OmegaClaw Core', 'agent loop, provider registry, directive layer', palette.cyan],
        ['GoalChainer', 'goal coverage, deontic status, action ranking', palette.green],
        ['PeTTaChainer', 'generated context, proof ladder, replay audit', palette.amber]
      ].map(([title, body, color]) => (
        <div key={title} style={{borderLeft: `8px solid ${color}`, padding: '18px 22px', background: palette.panel2, borderRadius: 8}}>
          <div style={{fontSize: 30, fontWeight: 800}}>{title}</div>
          <div style={{color: palette.muted, fontSize: 22, marginTop: 8}}>{body}</div>
        </div>
      ))}
    </div>
  );
};

const Pill: React.FC<{children: ReactNode; color: string}> = ({children, color}) => (
  <div
    style={{
      border: `2px solid ${color}`,
      borderRadius: 999,
      color,
      fontSize: 24,
      fontWeight: 800,
      padding: '12px 20px'
    }}
  >
    {children}
  </div>
);

const SignalCard: React.FC<{title: string; body: string; accent: string}> = ({title, body, accent}) => (
  <div style={{...card, minHeight: 320, padding: 34}}>
    <div style={{height: 10, width: 120, background: accent, borderRadius: 8, marginBottom: 28}} />
    <div style={{fontSize: 34, fontWeight: 800}}>{title}</div>
    <div style={{fontSize: 28, color: palette.muted, lineHeight: 1.25, marginTop: 22}}>{body}</div>
  </div>
);

const TerminalPanel: React.FC<{title: string; lines: string[]}> = ({title, lines}) => (
  <div style={{...card, overflow: 'hidden'}}>
    <div style={{background: '#0d1726', borderBottom: `1px solid ${palette.line}`, padding: '18px 26px', fontSize: 24, fontWeight: 800}}>
      {title}
    </div>
    <div style={{fontFamily: 'JetBrains Mono, Menlo, monospace', fontSize: 25, lineHeight: 1.55, padding: 30}}>
      {lines.map((line) => (
        <div key={line} style={{color: line.startsWith('$') ? palette.green : palette.text}}>
          {line}
        </div>
      ))}
    </div>
  </div>
);

const FeatureMatrix: React.FC<{rows: [string, string][]}> = ({rows}) => (
  <div style={{...card, padding: 30}}>
    {rows.map(([label, value]) => (
      <div key={label} style={{display: 'grid', gridTemplateColumns: '0.42fr 0.58fr', gap: 20, borderBottom: `1px solid ${palette.line}`, padding: '18px 0'}}>
        <div style={{color: palette.amber, fontSize: 24, fontWeight: 800}}>{label}</div>
        <div style={{fontSize: 24, color: palette.text}}>{value}</div>
      </div>
    ))}
  </div>
);

const DecisionRow: React.FC<{decision: (typeof decisions)[number]; index: number}> = ({decision, index}) => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [index * 10, index * 10 + 28], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  const visibleScore = decision.score < 0 ? 0.05 : decision.score * progress;
  const color = decision.status === 'recommended' ? palette.green : decision.status === 'blocked' ? palette.rose : palette.amber;
  return (
    <div style={{...card, padding: 28, display: 'grid', gridTemplateColumns: '0.36fr 0.2fr 0.44fr', gap: 24, alignItems: 'center'}}>
      <div>
        <div style={{fontSize: 32, fontWeight: 800}}>{decision.action}</div>
        <div style={{fontSize: 22, color: palette.muted, marginTop: 6}}>norm={decision.norm}</div>
      </div>
      <div style={{color, fontSize: 30, fontWeight: 900, textTransform: 'uppercase'}}>{decision.status}</div>
      <div>
        <div style={{height: 24, background: '#07101d', borderRadius: 999, overflow: 'hidden'}}>
          <div style={{height: '100%', width: `${Math.max(5, visibleScore * 100)}%`, background: color, borderRadius: 999}} />
        </div>
        <div style={{display: 'flex', justifyContent: 'space-between', marginTop: 12, color: palette.muted, fontSize: 20}}>
          <span>score {decision.score.toFixed(3)}</span>
          <span>individual {decision.individual.toFixed(1)} | collective {decision.collective.toFixed(1)}</span>
        </div>
      </div>
    </div>
  );
};

const Metric: React.FC<{label: string; value: string}> = ({label, value}) => (
  <div style={{background: palette.panel2, borderRadius: 8, padding: 20, minHeight: 118}}>
    <div style={{fontSize: 36, fontWeight: 900, color: palette.cyan}}>{value}</div>
    <div style={{fontSize: 18, color: palette.muted, marginTop: 8}}>{label}</div>
  </div>
);

const ProofLine: React.FC<{step: {label: string; value: string}; index: number}> = ({step, index}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [index * 8, index * 8 + 14], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  return (
    <div style={{display: 'grid', gridTemplateColumns: '70px 1fr', gap: 18, opacity, marginBottom: 16, alignItems: 'start'}}>
      <div style={{color: palette.amber, fontSize: 24, fontWeight: 900}}>{step.label}</div>
      <div style={{fontSize: 24, color: palette.text}}>{step.value}</div>
    </div>
  );
};

const HashLine: React.FC<{label: string; value: string}> = ({label, value}) => (
  <div style={{display: 'grid', gridTemplateColumns: '250px 1fr', gap: 18, marginTop: 16, color: palette.muted, fontFamily: 'JetBrains Mono, Menlo, monospace', fontSize: 15}}>
    <span>{label}</span>
    <span>{value}</span>
  </div>
);

const PlaceholderBox: React.FC<{title: string; detail: string; height?: number}> = ({title, detail, height = 520}) => (
  <div
    style={{
      ...card,
      alignItems: 'center',
      border: `4px dashed ${palette.violet}`,
      display: 'flex',
      flexDirection: 'column',
      height,
      justifyContent: 'center',
      padding: 42,
      textAlign: 'center' as CSSProperties['textAlign']
    }}
  >
    <div style={{fontSize: 38, fontWeight: 900}}>{title}</div>
    <div style={{fontSize: 26, color: palette.muted, lineHeight: 1.3, marginTop: 22, maxWidth: 620}}>{detail}</div>
  </div>
);

const ClipOrPlaceholder: React.FC<{title: string; detail: string; src: string | null; height?: number}> = ({
  title,
  detail,
  src,
  height = 520
}) => {
  if (!src) {
    return <PlaceholderBox detail={detail} height={height} title={title} />;
  }
  return (
    <div
      style={{
        ...card,
        border: `3px solid ${palette.violet}`,
        height,
        background: '#07101d',
        overflow: 'hidden',
        position: 'relative'
      }}
    >
      <OffthreadVideo
        muted
        src={staticFile(src)}
        style={{
          height: '100%',
          objectFit: 'contain',
          width: '100%'
        }}
      />
      <div
        style={{
          background: 'rgba(8, 17, 31, 0.78)',
          border: `1px solid ${palette.line}`,
          borderRadius: 8,
          left: 16,
          padding: '8px 12px',
          position: 'absolute',
          top: 16
        }}
      >
        <div style={{fontSize: 20, fontWeight: 900}}>{title}</div>
      </div>
    </div>
  );
};
