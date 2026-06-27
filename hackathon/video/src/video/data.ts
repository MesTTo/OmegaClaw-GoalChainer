export type Decision = {
  action: string;
  status: string;
  score: number;
  individual: number;
  collective: number;
  evidence: number;
  norm: string;
};

export type ProofStep = {
  label: string;
  value: string;
};

export const decisions: Decision[] = [
  {
    action: 'Publish redacted summary',
    status: 'recommended',
    score: 0.962342,
    individual: 1,
    collective: 1,
    evidence: 0.9009,
    norm: 'obligated'
  },
  {
    action: 'Hold external update',
    status: 'weak',
    score: 0.371658,
    individual: 1,
    collective: 0,
    evidence: 0.5742,
    norm: 'permitted'
  },
  {
    action: 'Publish raw incident log',
    status: 'blocked',
    score: -1,
    individual: 0,
    collective: 1,
    evidence: 0.1782,
    norm: 'forbidden'
  }
];

export const proofSteps: ProofStep[] = [
  {label: '01', value: 'Alert says a laptop credential touched CustomerDB'},
  {label: '02', value: 'CustomerDB is a critical asset'},
  {label: '03', value: 'Policy says critical compromise requires isolation'},
  {label: '04', value: 'Secondary signal recommends credential rotation'},
  {label: '05', value: 'Distractor paths are present but do not enter the proof'},
  {label: '06', value: 'Counterfactual removal drops the isolation conclusion'}
];

export const auditStats = [
  {label: 'Facts', value: '29'},
  {label: 'Rules', value: '4'},
  {label: 'Distractor trust edges', value: '15'},
  {label: 'Showcase checks', value: '11/11'},
  {label: 'Bundle verification', value: '9/9'},
  {label: 'Replay verification', value: '13/13'}
];

export const hashes = {
  scenario: '71e8f390cbd782eb89e41e710e49bbcfedbd197882956205c83fffa5e015bc53',
  proof: 'c97f8beeb2530e29bb761a1cbe7fca6c48316fc01cc70998121b50c71cdc6c64'
};
