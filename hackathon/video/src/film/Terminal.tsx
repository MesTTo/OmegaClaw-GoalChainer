import type {ReactNode} from 'react';
import {useCurrentFrame, interpolate} from 'remotion';
import {c, fonts, term} from './theme';

const RULES: [RegExp, string][] = [
  [/publish_redacted_summary/g, c.bright],
  [/publish_raw_log/g, c.red],
  [/hold_external_update/g, c.collective],
  [/forbidden|blocked|\[redacted\]/g, c.red],
  [/obligated/g, c.amber],
  [/recommended/g, c.teal],
  [/permitted|candidate|\bweak\b/g, c.dim],
  [/safe=True|PASS|\[ok\]|leaked=\[\]/g, c.green],
  [/-?\d+\.\d{2,}/g, c.amber],
];

const hl = (line: string): ReactNode[] => {
  const hits: {s: number; e: number; color: string}[] = [];
  for (const [re, color] of RULES) {
    re.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(line))) hits.push({s: m.index, e: m.index + m[0].length, color});
  }
  hits.sort((a, b) => a.s - b.s);
  const out: ReactNode[] = [];
  let i = 0;
  let k = 0;
  for (const h of hits) {
    if (h.s < i) continue;
    if (h.s > i) out.push(<span key={k++}>{line.slice(i, h.s)}</span>);
    out.push(
      <span key={k++} style={{color: h.color}}>
        {line.slice(h.s, h.e)}
      </span>,
    );
    i = h.e;
  }
  if (i < line.length) out.push(<span key={k++}>{line.slice(i)}</span>);
  return out;
};

const CMD_START = 6;
const CHARS_PER_FRAME = 1.1;
const REVEAL_GAP = 5;
const LINE_PER = 4.5;

export const cmdDone = (command: string) => CMD_START + command.length / CHARS_PER_FRAME;
export const lineVisibleAt = (command: string, j: number) =>
  cmdDone(command) + REVEAL_GAP + j * LINE_PER;

export const Terminal: React.FC<{label: string; command: string; lines: string[]}> = ({
  label,
  command,
  lines,
}) => {
  const frame = useCurrentFrame();
  const typed = Math.max(0, Math.min(command.length, Math.floor((frame - CMD_START) * CHARS_PER_FRAME)));
  const typing = frame >= CMD_START && typed < command.length;
  const done = cmdDone(command);
  const blink = Math.floor(frame / 15) % 2 === 0;

  return (
    <div
      style={{
        position: 'absolute',
        left: term.x,
        top: term.y,
        width: term.w,
        height: term.h,
        borderRadius: 14,
        background: `linear-gradient(180deg, ${c.panelTop}, ${c.panel})`,
        border: `1px solid ${c.edge}`,
        boxShadow: '0 40px 120px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.04)',
        overflow: 'hidden',
        fontFamily: fonts.mono,
      }}
    >
      {/* header */}
      <div
        style={{
          height: term.headerH,
          display: 'flex',
          alignItems: 'center',
          gap: 9,
          padding: '0 18px',
          borderBottom: `1px solid ${c.edge}`,
          background: 'rgba(255,255,255,0.015)',
        }}
      >
        {[c.red, c.amber, c.green].map((dot) => (
          <div key={dot} style={{width: 11, height: 11, borderRadius: 6, background: dot, opacity: 0.85}} />
        ))}
        <div style={{color: c.dim, fontSize: 15, letterSpacing: 0.4, marginLeft: 12}}>{label}</div>
        <div style={{flex: 1}} />
        <div style={{color: c.teal, fontSize: 13, letterSpacing: 1.5, opacity: 0.8}}>
          {typed < command.length ? 'RUNNING' : 'ON PeTTa'}
        </div>
      </div>

      {/* content */}
      <div
        style={{
          padding: `${term.padTop}px ${term.padX}px`,
          fontSize: term.fontSize,
          lineHeight: `${term.lineH}px`,
          color: c.text,
          whiteSpace: 'pre',
        }}
      >
        <div>
          <span style={{color: c.green}}>❯ </span>
          <span style={{color: c.bright, fontWeight: 600}}>{command.slice(0, typed)}</span>
          {typing && blink ? <span style={{color: c.teal}}>▋</span> : null}
        </div>
        {lines.map((line, j) => {
          const at = lineVisibleAt(command, j);
          if (frame < at) return null;
          const op = interpolate(frame, [at, at + 6], [0, 1], {extrapolateRight: 'clamp'});
          const dy = interpolate(frame, [at, at + 6], [6, 0], {extrapolateRight: 'clamp'});
          return (
            <div key={j} style={{opacity: op, transform: `translateY(${dy}px)`}}>
              {line === '' ? ' ' : hl(line)}
            </div>
          );
        })}
        {frame > done + REVEAL_GAP + lines.length * LINE_PER + 4 && blink ? (
          <span style={{color: c.teal}}>▋</span>
        ) : null}
      </div>
    </div>
  );
};
