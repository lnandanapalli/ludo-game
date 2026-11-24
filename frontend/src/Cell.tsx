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

  const groups = new Map<Pawn['color'], Pawn[]>()
  for (const pawn of pawns) {
    const group = groups.get(pawn.color)
    if (group) group.push(pawn)
    else groups.set(pawn.color, [pawn])
  }

  return (
    <div
      className={`ludo-board-cell cell--${type}`}
      data-color={color ?? undefined}
      id={`r${row}c${col}`}
    >
      {pawns.length > 0 && (
        <div className="pawn-layer" data-groups={groups.size}>
          {Array.from(groups, ([groupColor, group]) => (
            <div className="pawn-stack" key={groupColor} style={{ color: PAWN_COLOR_HEX[groupColor] }}>
              {group.map((pawn, index) => {
                const offset = index - (group.length - 1) / 2
                return (
                  <span
                    key={pawn.id}
                    className="pawn-icon"
                    style={{ transform: `translate(${offset * 19}%, ${offset * 5}%)` }}
                    role="img"
                    aria-label={`${groupColor} pawn`}
                  />
                )
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default Cell
