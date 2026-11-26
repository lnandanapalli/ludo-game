import { useEffect, useRef } from 'react'

const COLORS = ['#ed1b24', '#39b54a', '#fff201', '#00aeee', '#ffffff', '#f5d783']
const DURATION = 4200

/** A one-off burst of confetti over the whole window. Skipped when the viewer prefers reduced motion. */
export default function Confetti() {
  const canvas = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const element = canvas.current
    const context = element?.getContext('2d')
    if (!element || !context || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const ratio = window.devicePixelRatio || 1
    const resize = () => {
      element.width = innerWidth * ratio
      element.height = innerHeight * ratio
      context.setTransform(ratio, 0, 0, ratio, 0, 0)
    }
    resize()
    window.addEventListener('resize', resize)
    const pieces = Array.from({ length: Math.min(220, Math.round(innerWidth / 5)) }, (_, i) => ({
      x: innerWidth * (i % 2 ? 0.15 : 0.85) + (Math.random() - 0.5) * 80,
      y: innerHeight * 0.75,
      vx: (i % 2 ? 1 : -1) * (2 + Math.random() * 6),
      vy: -(9 + Math.random() * 9),
      size: 6 + Math.random() * 6,
      spin: Math.random() * Math.PI,
      turn: (Math.random() - 0.5) * 0.3,
      wobble: Math.random() * 10,
      color: COLORS[i % COLORS.length],
    }))
    const started = performance.now()
    let frame = 0
    const draw = (now: number) => {
      const elapsed = now - started
      context.clearRect(0, 0, innerWidth, innerHeight)
      context.globalAlpha = Math.min(1, (DURATION - elapsed) / 800)
      for (const piece of pieces) {
        piece.vy = Math.min(piece.vy + 0.32, 5)
        piece.vx *= 0.985
        piece.x += piece.vx + Math.sin((elapsed / 300) + piece.wobble) * 0.6
        piece.y += piece.vy
        piece.spin += piece.turn
        context.save()
        context.translate(piece.x, piece.y)
        context.rotate(piece.spin)
        context.scale(1, Math.cos(piece.spin * 2))
        context.fillStyle = piece.color
        context.fillRect(-piece.size / 2, -piece.size / 4, piece.size, piece.size / 2)
        context.restore()
      }
      if (elapsed < DURATION) frame = requestAnimationFrame(draw)
      else context.clearRect(0, 0, innerWidth, innerHeight)
    }
    frame = requestAnimationFrame(draw)
    return () => { cancelAnimationFrame(frame); window.removeEventListener('resize', resize) }
  }, [])
  return <canvas ref={canvas} className="confetti" aria-hidden="true" />
}
