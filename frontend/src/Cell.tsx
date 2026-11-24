import './Cell.css'
import { getCellInfo } from './colorLogic'
import { PAWN_COLOR_HEX, type Pawn } from './types'

interface CellProps {
  row: number
  col: number
  pawns: Pawn[]
}

function Cell({ row, col, pawns }: CellProps) {
  const { type, color } = getCellInfo(row, col)

  return (
    <div
      className={`ludo-board-cell cell--${type}`}
      data-color={color ?? undefined}
      id={`r${row}c${col}`}
    >
      {pawns.length > 0 && (
        <div className={`pawn-layer${pawns.length > 1 ? ' pawn-layer--multi' : ''}`}>
          {pawns.map(p => (
            <span
              key={p.id}
              className="pawn-icon"
              style={{ color: PAWN_COLOR_HEX[p.color] }}
              role="img"
              aria-label={`${p.color} pawn`}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default Cell
