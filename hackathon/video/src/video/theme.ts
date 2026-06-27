import type {CSSProperties} from 'react';

export const palette = {
  bg: '#08111f',
  panel: '#101c2d',
  panel2: '#13263a',
  line: '#29445d',
  text: '#edf6ff',
  muted: '#9fb6c8',
  cyan: '#2fd6c9',
  amber: '#f7b955',
  green: '#67d391',
  rose: '#ff6f91',
  violet: '#a88bff',
  white: '#ffffff'
};

export const fontStack = 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif';

export const fullFrame: CSSProperties = {
  backgroundColor: palette.bg,
  color: palette.text,
  fontFamily: fontStack
};

export const card: CSSProperties = {
  background: palette.panel,
  border: `1px solid ${palette.line}`,
  borderRadius: 8,
  boxShadow: '0 24px 80px rgba(0, 0, 0, 0.28)'
};
