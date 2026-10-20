// Purpose: the label each retained composition shows above every frame: these videos record
// GoalChainer in June 2026, before its domain-request migration, and the skills, verdicts,
// PeTTaChainer audit and delivery they show are retired, not current behaviour.
import type React from 'react';
import {AbsoluteFill} from 'remotion';

export const HISTORICAL_TITLE = 'HISTORICAL';
export const HISTORICAL_DETAIL =
  'Recorded June 2026, before GoalChainer’s domain-request migration. The skills, verdicts, PeTTaChainer audit and delivery shown here are retired.';

// A badge in the top-right corner, clear of every scene's header, panels and callouts, on its own
// colours and font stack so it reads the same over the film's and the draft's themes.
// am[implements a-fh-label-1018@2f54e2]
export const HistoricalLabel: React.FC = () => (
  <div
    style={{
      position: 'absolute',
      top: 22,
      right: 24,
      maxWidth: 560,
      padding: '10px 16px 12px',
      borderRadius: 10,
      background: 'rgba(245, 166, 35, 0.96)',
      color: '#17120a',
      fontFamily: '"IBM Plex Sans", "Inter", ui-sans-serif, system-ui, sans-serif',
      boxShadow: '0 6px 24px rgba(0, 0, 0, 0.45)',
    }}
  >
    <div style={{fontSize: 22, fontWeight: 800, letterSpacing: 3}}>{HISTORICAL_TITLE}</div>
    <div style={{fontSize: 17, lineHeight: 1.3, marginTop: 4}}>{HISTORICAL_DETAIL}</div>
  </div>
);

// The composition with the historical label drawn over each of its frames, so a still or a
// clip cut from it carries the label too.
// am[implements a-fh-label-1018@2f54e2]
export const historical = <P extends object>(Composition: React.ComponentType<P>): React.FC<P> => {
  const Labelled: React.FC<P> = (props) => (
    <AbsoluteFill>
      <Composition {...props} />
      <HistoricalLabel />
    </AbsoluteFill>
  );
  Labelled.displayName = `Historical(${Composition.displayName ?? Composition.name})`;
  return Labelled;
};
