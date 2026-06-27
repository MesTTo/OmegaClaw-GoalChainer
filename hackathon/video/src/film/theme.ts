import type {CSSProperties} from 'react';

// A cold reasoning-instrument palette: near-black navy, semantic accents that
// carry meaning (red = forbidden, amber = obligated, green = verified), and two
// distinct hues for the individual vs collective tension.
export const c = {
  bg: '#06090f',
  bgGlow: '#0b1726',
  panel: '#0b111b',
  panelTop: '#0f1825',
  edge: '#1b2a3a',
  grid: 'rgba(86,130,170,0.06)',
  text: '#e9eff7',
  dim: '#5f7289',
  faint: '#3b4961',
  bright: '#f4f8fd',
  teal: '#36d7c6',
  amber: '#f0b54a',
  red: '#ff6b6b',
  green: '#54d89a',
  individual: '#ff9a76',
  collective: '#6aa8ff',
  serif: '#f5ede1',
} as const;

export const fonts = {
  mono: "'IBMPlexMono', ui-monospace, SFMono-Regular, Menlo, monospace",
  serif: "'Fraunces', Georgia, 'Times New Roman', serif",
  sans: "'IBMPlexSans', ui-sans-serif, system-ui, sans-serif",
};

// Terminal geometry, shared so annotations can point at a given line.
export const term = {
  x: 96,
  y: 176,
  w: 980,
  h: 824,
  headerH: 46,
  padX: 30,
  padTop: 26,
  fontSize: 22,
  lineH: 33,
};

export const lineY = (index: number): number =>
  term.y + term.headerH + term.padTop + index * term.lineH + term.lineH / 2;

export const fill: CSSProperties = {
  position: 'absolute',
  inset: 0,
};
