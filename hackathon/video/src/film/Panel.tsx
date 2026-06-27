import type {ReactNode} from 'react';
import {c, fonts} from './theme';

// The window chrome shared by the reconstructed Terminal and the clip ClipPanel: a
// rounded panel with the three traffic-light dots, a label, and a right-aligned
// status. The content (typed lines or a video) is passed as children.

export const HEADER_H = 46;

export const PanelChrome: React.FC<{
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  status: string;
  children: ReactNode;
}> = ({x, y, w, h, label, status, children}) => (
  <div
    style={{
      position: 'absolute',
      left: x,
      top: y,
      width: w,
      height: h,
      borderRadius: 14,
      background: `linear-gradient(180deg, ${c.panelTop}, ${c.panel})`,
      border: `1px solid ${c.edge}`,
      boxShadow: '0 40px 120px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.04)',
      overflow: 'hidden',
      fontFamily: fonts.mono,
    }}
  >
    <div
      style={{
        height: HEADER_H,
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
      <div style={{color: c.teal, fontSize: 13, letterSpacing: 1.5, opacity: 0.85}}>{status}</div>
    </div>
    {children}
  </div>
);
