import './Cell.css'
import { getCellInfo } from './colorLogic'

interface CellProps {
  row: number
  col: number
}

function Cell({ row, col }: CellProps) {
  const { type, color } = getCellInfo(row, col)

  return (
    <div
      className={`ludo-board-cell cell--${type}`}
      data-color={color ?? undefined}
      id={`r${row}c${col}`}
    />
  )
}

export default Cell
