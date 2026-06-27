import {AbsoluteFill} from 'remotion';
import {c} from './theme';

// Deep navy with a faint blueprint grid and a soft top-left glow: an instrument
// panel, not a flat slide.
export const Background: React.FC = () => {
  return (
    <AbsoluteFill style={{backgroundColor: c.bg}}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(1200px 700px at 18% -8%, ${c.bgGlow} 0%, rgba(11,23,38,0) 60%)`,
        }}
      />
      <AbsoluteFill
        style={{
          backgroundImage: `linear-gradient(${c.grid} 1px, transparent 1px), linear-gradient(90deg, ${c.grid} 1px, transparent 1px)`,
          backgroundSize: '48px 48px',
          maskImage: 'radial-gradient(120% 120% at 50% 40%, #000 30%, transparent 100%)',
          WebkitMaskImage: 'radial-gradient(120% 120% at 50% 40%, #000 30%, transparent 100%)',
        }}
      />
      <AbsoluteFill
        style={{
          boxShadow: 'inset 0 0 320px rgba(0,0,0,0.6)',
        }}
      />
    </AbsoluteFill>
  );
};
