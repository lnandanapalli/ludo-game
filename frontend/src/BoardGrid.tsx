import './Board.css'
import Cell from './Cell'
import type { Pawn } from './types'

export default function BoardGrid({ pawns }: { pawns: Pawn[] }) {
  return (
      <table className="ludo-board">
        <tbody>
          {Array.from({ length: 15 }).map((_, r) => (
            <tr key={r}>
              {Array.from({ length: 15 }).map((_, c) => {
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
  )
}
