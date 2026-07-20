import './Board.css'
import Cell from './Cell'

function Board() {
  const rows = 15
  const cols = 15

  return (
    <table className="ludo-board">
      <tbody>
        {Array.from({ length: rows }).map((_, r) => (
          <tr key={r}>
            {Array.from({ length: cols }).map((_, c) => (
              <td key={c}>
                <Cell row={r} col={c} />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default Board
