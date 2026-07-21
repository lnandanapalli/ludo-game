import { useState } from 'react'
import './Board.css'
import Cell from './Cell'
import type { Pawn } from './types'

// Starting positions match the yard-pawn slots
const INITIAL_PAWNS: Pawn[] = [
  { id: 'red-1', color: 'red', row: 2, col: 2 },
  { id: 'red-2', color: 'red', row: 2, col: 3 },
  { id: 'red-3', color: 'red', row: 3, col: 2 },
  { id: 'red-4', color: 'red', row: 3, col: 3 },

  { id: 'green-1', color: 'green', row: 2, col: 11 },
  { id: 'green-2', color: 'green', row: 2, col: 12 },
  { id: 'green-3', color: 'green', row: 3, col: 11 },
  { id: 'green-4', color: 'green', row: 3, col: 12 },

  { id: 'yellow-1', color: 'yellow', row: 11, col: 11 },
  { id: 'yellow-2', color: 'yellow', row: 11, col: 12 },
  { id: 'yellow-3', color: 'yellow', row: 12, col: 11 },
  { id: 'yellow-4', color: 'yellow', row: 12, col: 12 },

  { id: 'blue-1', color: 'blue', row: 11, col: 2 },
  { id: 'blue-2', color: 'blue', row: 11, col: 3 },
  { id: 'blue-3', color: 'blue', row: 12, col: 2 },
  { id: 'blue-4', color: 'blue', row: 12, col: 3 },
]

// Demo
const TEST_PATH = [
  { row: 6, col: 1 },
  { row: 6, col: 2 },
  { row: 6, col: 3 },
  { row: 6, col: 4 },
  { row: 6, col: 5 },
  { row: 5, col: 6 },
  { row: 6, col: 1 },
]

function Board() {
  const rows = 15
  const cols = 15
  const [pawns, setPawns] = useState<Pawn[]>(INITIAL_PAWNS)

  function movePawn(
    pawnId: string,
    path: Array<{ row: number; col: number }>,
    stepDelay = 200,
    onDone?: () => void
  ) {
    path.forEach((pos, i) => {
      setTimeout(() => {
        setPawns(prev =>
          prev.map(p => (p.id === pawnId ? { ...p, row: pos.row, col: pos.col } : p))
        )
        if (i === path.length - 1) onDone?.()
      }, (i + 1) * stepDelay)
    })
  }

  return (
    <div>
      <table className="ludo-board">
        <tbody>
          {Array.from({ length: rows }).map((_, r) => (
            <tr key={r}>
              {Array.from({ length: cols }).map((_, c) => {
                const cellPawns = pawns.filter(p => p.row === r && p.col === c)
                return (
                  <td key={c}>
                    <Cell row={r} col={c} pawns={cellPawns} />
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>

      <button onClick={() => movePawn('red-1', TEST_PATH)}>
        Test move (red pawn)
      </button>
    </div>
  )
}

export default Board
