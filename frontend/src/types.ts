export type PawnColor = 'red' | 'green' | 'yellow' | 'blue'

export interface Pawn {
  id: string
  color: PawnColor
  row: number
  col: number
}

export const PAWN_COLOR_HEX: Record<PawnColor, string> = {
  red: '#ed1b24',
  green: '#39b54a',
  yellow: '#fff201',
  blue: '#00aeee',
}
