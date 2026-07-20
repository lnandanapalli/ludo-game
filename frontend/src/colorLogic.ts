export type CellType = 'yard' | 'path' | 'lane' | 'center' | 'empty' | 'start' | 'safe' | 'yard-empty' | 'yard-pawn'
export type Color = 'red' | 'green' | 'yellow' | 'blue' | null

export interface CellInfo {
  type: CellType
  color: Color
}

const YARD_EMPTY_CELLS = new Set([
  '1,1', '1,2', '1,3', '1,4', '1,10', '1,11', '1,12', '1,13',
  '2,1', '2,4', '2,10', '2,13',
  '3,1', '3,4', '3,10', '3,13',
  '4,1', '4,2', '4,3', '4,4', '4,10', '4,11', '4,12', '4,13',
])

const YARD_PAWN_CELLS = new Set([
  '2,2', '2,3', '3,2', '3,3'
])

function getYardCellInfo(row: number, col: number, rowStart: number, colStart: number, color: Color): CellInfo {
  const relRow = row - rowStart
  const relCol = col - colStart
  const key = `${relRow},${relCol}`

  if (YARD_EMPTY_CELLS.has(key)) return { type: 'yard-empty', color: null }
  else if (YARD_PAWN_CELLS.has(key)) return {type: 'yard-pawn', color}
  else return { type: 'yard', color }
}

export function getCellInfo(row: number, col: number): CellInfo {
  // Enclosure cells for Each payer's pawns and pawn cells
  if (row <= 5 && col <= 5) return getYardCellInfo(row, col, 0, 0, 'red')
  if (row <= 5 && col >= 9) return getYardCellInfo(row, col, 0, 9, 'green')
  if (row >= 9 && col >= 9) return getYardCellInfo(row, col, 9, 9, 'yellow')
  if (row >= 9 && col <= 5) return getYardCellInfo(row, col, 9, 0, 'blue')

  if (row >= 6 && row <= 8 && col >= 6 && col <= 8) {
    const isCenterCorner =
      (row === 6 && col === 6) ||
      (row === 6 && col === 8) ||
      (row === 8 && col === 6) ||
      (row === 8 && col === 8)

    if (isCenterCorner) return { type: 'empty', color: null }

    if (row === 6 && col === 7) return { type: 'center', color: 'green' }
    if (row === 7 && col === 8) return { type: 'center', color: 'yellow' }
    if (row === 8 && col === 7) return { type: 'center', color: 'blue' }
    if (row === 7 && col === 6) return { type: 'center', color: 'red' }

    return { type: 'empty', color: null }
  }

  if (row === 6 && col === 1) return { type: 'start', color: 'red' }
  if (row === 1 && col === 8) return { type: 'start', color: 'green' }
  if (row === 8 && col === 13) return { type: 'start', color: 'yellow' }
  if (row === 13 && col === 6) return { type: 'start', color: 'blue' }

  // Pawn cannot be killed on these
  if (row === 2 && col === 6) return { type: 'safe', color: 'red' }
  if (row === 6 && col === 12) return { type: 'safe', color: 'green' }
  if (row === 12 && col === 8) return { type: 'safe', color: 'yellow' }
  if (row === 8 && col === 2) return { type: 'safe', color: 'blue' }

  // Lane to reach center square
  if (row === 7 && col >= 1 && col <= 5) return { type: 'lane', color: 'red' }
  if (col === 7 && row >= 1 && row <= 5) return { type: 'lane', color: 'green' }
  if (row === 7 && col >= 9 && col <= 13) return { type: 'lane', color: 'yellow' }
  if (col === 7 && row >= 9 && row <= 13) return { type: 'lane', color: 'blue' }

  // Shared path
  return { type: 'path', color: null }
}
