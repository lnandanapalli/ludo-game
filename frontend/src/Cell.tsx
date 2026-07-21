import './Cell.css'
import { getCellInfo } from './colorLogic'
import { MapPin } from 'lucide-react'
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
            <MapPin
              key={p.id}
              className="pawn-icon"
              fill={PAWN_COLOR_HEX[p.color]}
              stroke="#000"
              strokeWidth={1.5}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default Cell
