import {c} from './theme';
import {lineVisibleAt, cmdDone} from './Terminal';
import type {Note} from './Annotation';
import type {Callout} from './Clip';

export type Scene = {
  id: string;
  label: string;
  duration: number;
  // A reconstructed terminal scene (typed output + line-pointing annotations) ...
  command?: string;
  lines?: string[];
  notes?: Note[];
  // ... or a real screen recording with side callouts.
  clip?: string;
  clipLabel?: string;
  playbackRate?: number;
  callouts?: Callout[];
};

const hold = 150;

// ── Scene: omegaclaw ── the headline, as a real recording. This is the captured
// codex_drives_omegaclaw.sh session (public/recordings/codex-omegaclaw.mp4): Codex
// reads OmegaClaw's skill menu and the incident, reasons, emits goalchainer-solve on
// its own, and OmegaClaw's own registry evaluates it. The callouts mark the three
// moments; the terminal is the genuine run, not a reconstruction.
const omegaclaw: Scene = {
  id: 'omegaclaw',
  label: 'goalchainer — a real OmegaClaw Core run, driven by Codex',
  clip: 'recordings/codex-omegaclaw.mp4',
  clipLabel: 'OmegaClaw Core · Codex provider · GoalChainer skill',
  playbackRate: 1,
  callouts: [
    {
      at: 52,
      cardY: 196,
      accent: c.teal,
      label: 'the agent · live',
      title: 'This is Codex, actually running.',
      body: 'OpenAI Codex v0.139.0, model gpt-5.5, reasoning effort xhigh. OmegaClaw hands it the skill menu and the incident as one cycle of its loop.',
    },
    {
      at: 196,
      cardY: 446,
      accent: c.bright,
      label: 'it chooses',
      title: 'It reasons, then emits goalchainer-solve.',
      body: 'Codex weighs which skill fits the request, then emits one command. The choice is the model’s, drawn from the menu, not a script.',
    },
    {
      at: 330,
      cardY: 696,
      accent: c.green,
      label: 'omegaclaw evaluates',
      title: 'Raw log blocked. Output leak-checked.',
      body: 'OmegaClaw’s own registry runs the command: lib_deontic forbids the raw log, MetaMo picks the redacted summary, and the deliverable is scanned clean.',
    },
  ],
  duration: 420,
};

// ── Scene: validate ── proof the decision is a function of the input.
const vCmd = 'goalchainer validate';
const vLines = [
  'input-sensitivity battery: PASS',
  '',
  '[pii_incident]   sensitive data present',
  '   blocked  -1.000  publish_raw_log  (deontic=forbidden)',
  '[public_no_data]   declared safe to share',
  'recommended  0.847  publish_raw_log  (deontic=permitted)',
  '[facts_not_ready]   sensitive, facts not ready',
  ' candidate  0.528  hold_external_update  (deontic=obligated)',
  '',
  'raw-log status by case:',
  '  pii_incident    : forbidden',
  '  public_no_data  : permitted',
  '  facts_not_ready : forbidden',
];
const validate: Scene = {
  id: 'validate',
  label: 'goalchainer — is the decision real?',
  command: vCmd,
  lines: vLines,
  notes: [
    {
      at: lineVisibleAt(vCmd, 12) + 18,
      line: 10,
      cardY: 250,
      accent: c.teal,
      label: 'evidence · not a fixed answer',
      title: 'The same code. Three requests. Three verdicts.',
      body: 'Publishing the raw log is forbidden when the data is sensitive, permitted when the request says it is public. The decision is a function of the input, not a script.',
    },
  ],
  duration: lineVisibleAt(vCmd, 12) + 18 + hold,
};

// ── Scene: motivation ── individual vs collective, reconciled.
const mCmd = 'goalchainer motivation';
const mLines = [
  'MetaMo consensus — individual vs collective (on PeTTa)',
  '  individual goals pull toward: publish_redacted_summary',
  '  collective goals pull toward: publish_raw_log',
  '  risk-weighted consensus:      publish_redacted_summary',
];
const motivation: Scene = {
  id: 'motivation',
  label: 'goalchainer — whose goals?',
  command: mCmd,
  lines: mLines,
  notes: [
    {
      at: lineVisibleAt(mCmd, 2) + 16,
      line: 2,
      cardY: 250,
      accent: c.collective,
      label: 'the collective',
      title: 'The team wants the raw log.',
      body: 'Repair and coordination pull toward the most detail. Each goal owner is its own OpenPsi motivation subsystem in MetaMo.',
    },
    {
      at: lineVisibleAt(mCmd, 2) + 100,
      line: 1,
      cardY: 470,
      accent: c.individual,
      title: 'The person wants to hold.',
      label: 'the individual',
      body: 'Privacy pulls the other way. Two owners, two motivations, in genuine conflict.',
    },
    {
      at: lineVisibleAt(mCmd, 2) + 190,
      line: 3,
      cardY: 690,
      accent: c.teal,
      label: 'reconciled',
      title: 'The consensus penalizes disagreement.',
      body: 'MetaMo picks the action both can accept — the redacted summary — scoring (a+b)/2 minus the gap between them.',
    },
  ],
  duration: lineVisibleAt(mCmd, 2) + 190 + hold,
};

// ── Scene: solve ── decide AND execute, verified.
const sCmd = 'goalchainer solve';
const sLines = [
  'decided: Publish redacted summary (recommended)',
  'executed on real incident data',
  'raw log has: customer_email, order_id, access_token, stack_trace',
  'channel: external',
  'safe deliverable:',
  '{',
  '  "service": "checkout",',
  '  "status": "degraded",',
  '  "summary": "Checkout payment retries are timing out.",',
  '  "diagnostics": {',
  '    "customer_email": "[redacted]",',
  '    "order_id": "[redacted]",',
  '    "access_token": "[redacted]",',
  '    "stack_trace": "[redacted]",',
  '    "error_code": "PAYMENT_TIMEOUT"',
  '  },',
  '  "next_update": "15 minutes"',
  '}',
  'leak check: safe=True  leaked=[]',
];
const solve: Scene = {
  id: 'solve',
  label: 'goalchainer — does it actually solve it?',
  command: sCmd,
  lines: sLines,
  notes: [
    {
      at: lineVisibleAt(sCmd, 2) + 16,
      line: 2,
      cardY: 250,
      accent: c.red,
      label: 'real data in',
      title: 'Real PII goes in.',
      body: 'Customer emails, order IDs, access tokens, a stack trace — the actual raw incident log, not a placeholder.',
    },
    {
      at: lineVisibleAt(sCmd, 18) + 18,
      line: 18,
      cardY: 560,
      accent: c.green,
      label: 'safe deliverable out · verified',
      title: 'Out comes the artifact to send.',
      body: 'Every restricted value redacted, the operational error code kept. The leak check scans the output for the actual secrets and confirms none survive.',
    },
  ],
  duration: lineVisibleAt(sCmd, 18) + 18 + hold + 20,
};

export const scenes: Scene[] = [omegaclaw, validate, motivation, solve];
export {cmdDone};
