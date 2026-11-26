import { useState } from 'react'
import './Die.css'

const pips = [[4], [0, 8], [0, 4, 8], [0, 2, 6, 8], [0, 2, 4, 6, 8], [0, 2, 3, 5, 6, 8]]
// Cube rotation that turns each value's face toward the viewer (faces are placed in Die.css).
const facing: Record<number, [number, number]> = { 1: [0, 0], 2: [0, -90], 3: [-90, 0], 4: [90, 0], 5: [0, 90], 6: [0, 180] }

function Face({ value }: { value: number }) {
  return <span className="die-face" data-face={value}>
    {pips[value - 1].map(index =>
      <i key={index} style={{ gridRow: Math.floor(index / 3) + 1, gridColumn: index % 3 + 1 }} />)}
  </span>
}

/** A 3D die. While `rolling` it tumbles; afterwards it spins forward onto `value`. */
export default function Die({ value, rolling = false }: { value: number; rolling?: boolean }) {
  const shown = value || 1
  // Each new result adds whole turns so the cube rolls into place instead of snapping.
  const [turns, setTurns] = useState({ value: shown, rolling, count: 0 })
  if (turns.value !== shown || turns.rolling !== rolling)
    setTurns({ value: shown, rolling, count: turns.count + Number(turns.rolling && !rolling || turns.value !== shown) })
  const [x, y] = facing[shown]
  const spin = turns.count * 360
  return <span className="die-3d" aria-hidden="true">
    <span className="cube" data-value={shown} data-rolling={rolling || undefined}
      style={{ transform: `rotateX(${x + spin}deg) rotateY(${y + spin}deg)` }}>
      {/* A solid core just inside the faces, so the rounded corners never show through the die. */}
      {[1, 2, 3, 4, 5, 6].map(face => <span key={'core' + face} className="die-core" data-face={face} />)}
      {[1, 2, 3, 4, 5, 6].map(face => <Face key={face} value={face} />)}
    </span>
  </span>
}
