import {c} from './theme';
import {lineVisibleAt, cmdDone} from './Terminal';
import type {Note} from './Annotation';
import type {Callout, Step} from './Clip';

export type Scene = {
  id: string;
  label: string;
  duration: number;
  // A reconstructed terminal scene (typed output + line-pointing annotations) ...
  command?: string;
  lines?: string[];
  notes?: Note[];
  // ... or a real screen recording with side callouts / step captions.
  clip?: string;
  clipLabel?: string;
  playbackRate?: number;
  callouts?: Callout[];
  steps?: Step[];
};

const hold = 240;

// ── Scene: omegaclaw ── the headline, as a real recording: the captured
// codex_omegaclaw_loop.sh session (public/recordings/codex-omegaclaw-loop.mp4).
// Codex is the provider in OmegaClaw's loop and works the incident across cycles,
// one command per turn: pin, then SNARS, MetaMo, the ranked decision, solve, and a
// grounded send. The step caption narrates whichever cycle is on screen. The
// terminal is the genuine run, not a reconstruction.
const omegaclaw: Scene = {
  id: 'omegaclaw',
  label: 'goalchainer — a real OmegaClaw Core run, driven by Codex',
  clip: 'recordings/codex-omegaclaw-loop.mp4',
  clipLabel: 'OmegaClaw Core · Codex provider · GoalChainer skill',
  playbackRate: 0.85,
  steps: [
    {
      at: 60,
      accent: c.teal,
      tag: 'step · pin',
      title: 'Codex takes the task.',
      body: 'OpenAI Codex v0.139.0 (gpt-5.5, reasoning effort xhigh) is the provider in OmegaClaw’s loop. It pins the task and works the GoalChainer skill, one command per cycle.',
    },
    {
      at: 430,
      accent: c.amber,
      tag: 'step · SNARS (deduce)',
      title: 'It asks SNARS for an opinion.',
      body: 'goalchainer-snars returns a Subjective-Logic verdict: sharing the raw log is a forbidden action, belief 0.67, uncertainty 0.33, with provenance. Codex reads it and continues.',
    },
    {
      at: 600,
      accent: c.collective,
      tag: 'step · MetaMo (reconcile)',
      title: 'It reconciles the goals.',
      body: 'goalchainer-motivation runs MetaMo: the individual pulls to the redacted summary, the collective to the raw log, and the disagreement-penalized consensus lands on redacted.',
    },
    {
      at: 920,
      accent: c.red,
      tag: 'step · decide',
      title: 'The ranked verdict blocks the raw log.',
      body: 'goalchainer-decision: publish_raw_log is forbidden by lib_deontic; publish_redacted_summary is recommended (0.987). The answer is now proof-backed, not a guess.',
    },
    {
      at: 1090,
      accent: c.green,
      tag: 'step · solve',
      title: 'It solves on the real data.',
      body: 'goalchainer-solve redacts every secret (emails, order IDs, tokens, stack trace), keeps the error code, and leak-checks the output: safe=True, leaked=[].',
    },
    {
      at: 1240,
      accent: c.bright,
      tag: 'step · deliver',
      title: 'It sends the grounded answer.',
      body: 'Codex posts the safe incident update to the channel, raw log withheld and the verdict behind it. Six cycles, one delivered answer.',
    },
  ],
  duration: 1500,
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
