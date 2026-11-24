import { useRef, useState } from 'react'
import './Board.css'
import BoardGrid from './BoardGrid'
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
  const [pawns, setPawns] = useState<Pawn[]>(INITIAL_PAWNS)

  const timers = useRef<number[]>([])

  function stopMove() {
    timers.current.forEach(window.clearTimeout)
    timers.current = []
  }

  function testMove() {
    stopMove()
    timers.current = TEST_PATH.map((position, index) =>
      window.setTimeout(() => {
        setPawns(previous => previous.map(pawn =>
          pawn.id === 'red-1' ? { ...pawn, ...position } : pawn
        ))
      }, (index + 1) * 200)
    )
  }

  function showStack(include: (pawn: Pawn) => boolean) {
    stopMove()
    setPawns(INITIAL_PAWNS.map(pawn =>
      include(pawn) ? { ...pawn, row: 6, col: 1 } : pawn
    ))
  }

  return (
    <div>
      <BoardGrid pawns={pawns} />

      <div className="demo-buttons">
        <button onClick={testMove}>Test move (red pawn)</button>
        <button onClick={() => showStack(p => p.color === 'red')}>Stack 4 red</button>
        <button onClick={() => showStack(p => ['red-1', 'red-2', 'red-3', 'blue-1', 'blue-2'].includes(p.id))}>
          Stack 3 red + 2 blue
        </button>
        <button onClick={() => showStack(p => p.id.endsWith('-1'))}>Stack 1 of each color</button>
        <button onClick={() => showStack(() => true)}>Stack all 16</button>
        <button onClick={() => showStack(() => false)}>Reset board</button>
      </div>
    </div>
  )
}

export default Board
