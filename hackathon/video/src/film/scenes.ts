import {c} from './theme';
import {lineVisibleAt, cmdDone} from './Terminal';
import type {Note} from './Annotation';

export type Scene = {
  id: string;
  label: string;
  command: string;
  lines: string[];
  notes: Note[];
  duration: number;
};

const hold = 150;

// ── Scene: omegaclaw ── the headline: GoalChainer is a real OmegaClaw Core skill,
// and a real agent (Codex) drives it. This is the captured codex_drives_omegaclaw.sh
// session: Codex reads OmegaClaw's skill menu and the incident and emits the command
// on its own; OmegaClaw's own registry evaluates it.
const ocCmd = 'bash integrations/omegaclaw/codex_drives_omegaclaw.sh';
const ocLines = [
  'OmegaClaw Core   provider: Codex   skills: OmegaClaw + GoalChainer',
  '',
  'HUMAN-MSG: Checkout is down. Engineers want to paste raw logs',
  '  with customer emails and order IDs into the public channel.',
  '',
  '>> sending the agent context to the provider (codex exec) ...',
  '',
  'codex (the agent) emits one command:',
  '  goalchainer-solve  Checkout is down. On-call engineers want',
  '  to paste raw logs with emails and order IDs ... produce the',
  '  safe incident-channel post.',
  '',
  'OmegaClaw evaluates it via its own skill registry:',
  '  decided   publish_redacted_summary   (recommended)',
  '  blocked   publish_raw_log   (lib_deontic: forbidden)',
  '  individual -> publish_redacted_summary',
  '  collective -> publish_raw_log',
  '  consensus (MetaMo): publish_redacted_summary',
  '  redacted: customer_email, order_id, access_token, +2',
  '  leak check: safe=True   leaked=[]',
];
const ocLast = lineVisibleAt(ocCmd, ocLines.length - 1);
const omegaclaw: Scene = {
  id: 'omegaclaw',
  label: 'goalchainer — runs as an OmegaClaw Core skill',
  command: ocCmd,
  lines: ocLines,
  notes: [
    {
      at: ocLast + 18,
      line: 9,
      cardY: 196,
      accent: c.teal,
      label: 'the agent chooses',
      title: 'Codex picks the skill itself.',
      body: 'OmegaClaw shows Codex its skill menu and the incident. Codex emits goalchainer-solve on its own, so the choice is the agent’s, not a script.',
    },
    {
      at: ocLast + 110,
      line: 15,
      cardY: 452,
      accent: c.red,
      label: 'omegaclaw · deontic',
      title: 'Its own logic forbids the raw log.',
      body: 'lib_deontic, the OmegaClaw-Core deontic layer, blocks the raw log. MetaMo then weighs the team’s pull against the person’s, and the consensus holds.',
    },
    {
      at: ocLast + 202,
      line: 20,
      cardY: 712,
      accent: c.green,
      label: 'verified',
      title: 'Redacted, then leak-checked.',
      body: 'OmegaClaw evaluates the verdict and returns the post to send, every secret stripped and a scan confirming none survive before it leaves.',
    },
  ],
  duration: ocLast + 202 + hold + 24,
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
