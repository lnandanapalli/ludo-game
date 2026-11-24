import './Board.css'
import Cell from './Cell'
import type { Pawn } from './types'

export default function BoardGrid({ pawns, moves }: { pawns: Pawn[]; moves?: Map<string, () => void> }) {
  return (
      <table className="ludo-board">
        <tbody>
          {Array.from({ length: 15 }).map((_, r) => (
            <tr key={r}>
              {Array.from({ length: 15 }).map((_, c) => {
                const cellPawns = pawns.filter(p => p.row === r && p.col === c)
                const choice = cellPawns.find(p => moves?.has(p.id))
                return (
                  <td key={c}>
                    <Cell row={r} col={c} pawns={cellPawns} playable={moves} />
                    {choice && <button className="board-choice" aria-label={`Move ${choice.id}`}
                      onClick={moves?.get(choice.id)} />}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
  )
}
