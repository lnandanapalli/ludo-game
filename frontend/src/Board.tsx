import './Board.css'
import { PAWN_COLOR_HEX, type Pawn, type PawnColor } from './types'

/* Geometry, in board cells (15 x 15). Mirrors backend/app/game.py. */
const QUARTER: [number, number][] = [[6, 1], [6, 2], [6, 3], [6, 4], [6, 5], [5, 6], [4, 6],
  [3, 6], [2, 6], [1, 6], [0, 6], [0, 7], [0, 8]]
const rotate = ([row, col]: [number, number], turns: number): [number, number] => {
  for (let i = 0; i < turns; i++) [row, col] = [col, 14 - row]
  return [row, col]
}
const ORDER: PawnColor[] = ['red', 'green', 'yellow', 'blue']
const TRACK = ORDER.flatMap((_, turn) => QUARTER.map(cell => rotate(cell, turn)))
const START = new Map(ORDER.map((color, turn) => [rotate([6, 1], turn).join(), color]))
const SAFE = new Set(ORDER.map((_, turn) => rotate([2, 6], turn).join()))
const LANES = ORDER.flatMap((color, turn) =>
  [1, 2, 3, 4, 5].map(step => ({ cell: rotate([7, step], turn), color })))
const YARDS = ORDER.map((color, turn) => ({ color, corner: rotate([0, 0], turn), spots:
  [0, 1, 2, 3].map(pawn => rotate([2 + (pawn >> 1), 2 + (pawn & 1)], turn)) }))

type Fill = { cell: [number, number]; fill: string }
const CELLS: Fill[] = [
  ...TRACK.map(cell => ({ cell, fill: START.has(cell.join()) ? PAWN_COLOR_HEX[START.get(cell.join())!]
    : SAFE.has(cell.join()) ? '#fff6d2' : '#ffffff' })),
  ...LANES.map(({ cell, color }) => ({ cell, fill: PAWN_COLOR_HEX[color] })),
]

// Every cell edge on the cross, drawn once so neighbouring cells never double a line.
const GRID = (() => {
  const edges = new Set<string>()
  for (const { cell: [r, c] } of CELLS) {
    edges.add(`M${c} ${r}h1`); edges.add(`M${c} ${r + 1}h1`)
    edges.add(`M${c} ${r}v1`); edges.add(`M${c + 1} ${r}v1`)
  }
  return [...edges].join('')
})()

// A five-pointed star centred in a cell.
const star = (r: number, c: number) => Array.from({ length: 10 }, (_, i) => {
  const radius = i % 2 ? 0.17 : 0.38
  const angle = -Math.PI / 2 + i * Math.PI / 5
  return `${(c + 0.5 + radius * Math.cos(angle)).toFixed(3)},${(r + 0.53 + radius * Math.sin(angle)).toFixed(3)}`
}).join(' ')

function Artwork() {
  return <svg className="board-art" viewBox="0 0 15 15" role="img" aria-label="Ludo board">
    <rect width="15" height="15" fill="#ffffff" />
    {YARDS.map(({ color, corner: [r, c], spots }) => {
      const top = r ? 9 : 0, left = c ? 9 : 0  // Yards fill the four 6 x 6 corners.
      return <g key={color}>
        <rect x={left} y={top} width="6" height="6" fill={PAWN_COLOR_HEX[color]} shapeRendering="crispEdges" />
        <rect x={left + 1} y={top + 1} width="4" height="4" rx="0.35" fill="#ffffff" />
        {spots.map(([sr, sc]) => <circle key={sr + '-' + sc} cx={sc + 0.5} cy={sr + 0.5} r="0.4"
          fill={PAWN_COLOR_HEX[color]} stroke="#00000022" strokeWidth="0.04" />)}
      </g>
    })}
    {CELLS.map(({ cell: [r, c], fill }) =>
      <rect key={r + '-' + c} x={c} y={r} width="1" height="1" fill={fill} shapeRendering="crispEdges" />)}
    {[...SAFE, ...START.keys()].map(key => {
      const [r, c] = key.split(',').map(Number)
      const start = START.has(key)
      return <polygon key={'star' + key} points={star(r, c)} fill={start ? '#ffffff' : 'none'}
        fillOpacity={start ? 0.85 : 1} stroke={start ? 'none' : '#a3822a'} strokeWidth="0.05" strokeLinejoin="round" />
    })}
    <polygon points="6,6 9,6 7.5,7.5" fill={PAWN_COLOR_HEX.green} />
    <polygon points="9,6 9,9 7.5,7.5" fill={PAWN_COLOR_HEX.yellow} />
    <polygon points="6,9 9,9 7.5,7.5" fill={PAWN_COLOR_HEX.blue} />
    <polygon points="6,6 6,9 7.5,7.5" fill={PAWN_COLOR_HEX.red} />
    <path className="board-lines" d={GRID} />
  </svg>
}

function Stack({ pawns, moves }: { pawns: Pawn[]; moves?: Map<string, () => void> }) {
  const groups = new Map<PawnColor, Pawn[]>()
  for (const pawn of pawns) groups.set(pawn.color, [...groups.get(pawn.color) ?? [], pawn])
  return <div className="pawn-layer" data-groups={groups.size}>
    {Array.from(groups, ([color, group]) =>
      <div className="pawn-stack" key={color} style={{ color: PAWN_COLOR_HEX[color] }}>
        {group.map((pawn, index) => {
          const offset = index - (group.length - 1) / 2
          return <span key={pawn.id} className="pawn-icon" role="img" aria-label={`${color} pawn`}
            data-playable={moves?.has(pawn.id) || undefined}
            style={{ transform: `translate(${offset * 19}%, ${offset * 5}%)` }} />
        })}
      </div>)}
  </div>
}

/** The board artwork with pawns and move targets laid over the same 15 x 15 grid. */
export default function Board({ pawns, moves }: { pawns: Pawn[]; moves?: Map<string, () => void> }) {
  const occupied = new Map<string, Pawn[]>()
  for (const pawn of pawns) {
    const key = pawn.row + ',' + pawn.col
    occupied.set(key, [...occupied.get(key) ?? [], pawn])
  }
  return <div className="ludo-board">
    <Artwork />
    <div className="board-pieces">
      {Array.from(occupied, ([key, here]) => {
        const [row, col] = key.split(',').map(Number)
        const choice = here.find(p => moves?.has(p.id))
        return <div key={key} className="board-cell" style={{ gridRow: row + 1, gridColumn: col + 1 }}>
          <Stack pawns={here} moves={moves} />
          {choice && <button className="board-choice" aria-label={`Move ${choice.id}`} onClick={moves?.get(choice.id)} />}
        </div>
      })}
    </div>
  </div>
}
