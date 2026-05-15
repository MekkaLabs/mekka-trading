export interface Squad {
  name: string;
  mandate: string;
  members: string[];
}

export const SQUADS: Squad[] = [
  {
    name: 'alpha-risk-command',
    mandate: 'Guarantee paper-only controls and pre-trade validations.',
    members: ['Batman', 'Nick Fury', 'Wolverine'],
  },
  {
    name: 'hyperliquid-mock-ops',
    mandate: 'Maintain safe mock exchange connectivity and execution rehearsal.',
    members: ['Iron Man', 'Professor X', 'Spider-Man'],
  },
  {
    name: 'market-intel-lab',
    mandate: 'Generate market context and anomaly signals for strategy experiments.',
    members: ['Superman', 'Doctor Strange', 'Vision', 'Thor', 'Aquaman', 'Flash', 'Black Panther', 'Deadpool'],
  },
];
