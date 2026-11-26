import { useLayoutEffect, useRef } from 'react'
import { EMOTE, portraitOf } from './emotes'
import { emoteSound } from './sound'
import type { PawnColor } from './types'
import './Chat.css'

export interface Show { key: number; emote: string; from: PawnColor; to: PawnColor | null }

const centre = (seat: PawnColor) => {
  const box = portraitOf(seat)?.getBoundingClientRect()
  return box && { x: box.left + box.width / 2, y: box.top + box.height / 2 }
}

function burst({ x, y, pieces, layer }: { x: number; y: number; pieces: string[]; layer: HTMLElement }) {
  pieces.forEach((piece, i) => {
    const bit = document.createElement('span')
    bit.className = 'emote-piece'
    bit.textContent = piece
    layer.appendChild(bit)
    const angle = (i / pieces.length) * Math.PI * 2 + Math.random()
    const reach = 34 + Math.random() * 18
    bit.animate([
      { transform: `translate(${x}px, ${y}px) translate(-50%, -50%) scale(.4)`, opacity: 1 },
      { transform: `translate(${x + Math.cos(angle) * reach}px, ${y + Math.sin(angle) * reach}px) translate(-50%, -50%) scale(1)`, opacity: 0 },
    ], { duration: 700, easing: 'cubic-bezier(.2,.8,.3,1)' }).onfinish = () => bit.remove()
  })
}

/** Plays one emote: a reaction over the sender, or a throw that travels to the target. */
function Play({ show, done }: { show: Show; done: (key: number) => void }) {
  const element = useRef<HTMLSpanElement>(null)
  useLayoutEffect(() => {
    const node = element.current
    const emote = EMOTE[show.emote]
    const from = centre(show.from)
    const to = show.to && centre(show.to)
    if (!node || !emote || !from) { done(show.key); return }
    const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const place = (x: number, y: number, extra = '') => `translate(${x}px, ${y}px) translate(-50%, -50%) ${extra}`
    let animation: Animation
    if (emote.kind === 'reaction' || !to) {
      // Rise above the picture, or drop below it when there is no room at the top of the screen.
      const up = from.y > 130 ? -1 : 1
      const at = (lift: number, extra = '') => place(from.x, from.y + up * lift, extra)
      animation = node.animate(calm ? [
        { transform: at(56), opacity: 1 }, { transform: at(56), opacity: 0, offset: 1 },
      ] : [
        { transform: at(24, 'scale(.2)'), opacity: 0 },
        { transform: at(58, 'scale(1.15)'), opacity: 1, offset: 0.18 },
        { transform: at(58, 'scale(1)'), opacity: 1, offset: 0.3 },
        { transform: at(70, 'scale(1)'), opacity: 1, offset: 0.85 },
        { transform: at(80, 'scale(.9)'), opacity: 0 },
      ], { duration: 2200, easing: 'ease-out' })
    } else {
      const dx = to.x - from.x, dy = to.y - from.y
      const heading = Math.atan2(dy, dx) * 180 / Math.PI
      // Turn the emoji's drawn direction toward the target, mirroring rather than flipping it upside down.
      const face = (emote.aim ?? 0)
      const mirror = emote.flight === 'wiggle' ? (dx > 0 ? 'scaleX(-1)' : '') : ''
      const turn = emote.flight === 'line' ? `rotate(${heading - face}deg)` : ''
      const steps = 24
      const frames: Keyframe[] = []
      for (let i = 0; i <= steps; i++) {
        const t = i / steps
        let x = from.x + dx * t, y = from.y + dy * t
        const length = Math.hypot(dx, dy) || 1
        const nx = -dy / length, ny = dx / length  // Perpendicular to the path.
        let extra = `${turn} ${mirror}`
        if (calm) { /* Straight and steady. */ }
        else if (emote.flight === 'wiggle') { const s = Math.sin(t * Math.PI * 6) * 12; x += nx * s; y += ny * s }
        else if (emote.flight === 'arc') { y -= Math.sin(t * Math.PI) * Math.min(160, length * 0.5); extra += ` rotate(${t * 540}deg)` }
        else if (emote.flight === 'float') { const s = Math.sin(t * Math.PI * 2) * 18; x += nx * s; y += ny * s; extra += ` scale(${1 + Math.sin(t * Math.PI * 4) * 0.12})` }
        frames.push({ transform: place(x, y, extra), opacity: i === 0 ? 0 : 1 })
      }
      animation = node.animate(frames, {
        duration: calm ? 900 : emote.flight === 'wiggle' ? 1700 : emote.flight === 'float' ? 1500 : 950,
        easing: emote.flight === 'line' ? 'cubic-bezier(.5,0,.75,0)' : 'ease-in-out', fill: 'forwards',
      })
      animation.finished.then(() => {
        const layer = node.parentElement
        if (layer && emote.impact && !calm) burst({ x: to.x, y: to.y, pieces: emote.impact, layer })
        if (!calm) portraitOf(show.to!)?.animate([
          { transform: 'translateX(0)' }, { transform: 'translateX(-5px) rotate(-6deg)' }, { transform: 'translateX(5px) rotate(6deg)' },
          { transform: 'translateX(-3px)' }, { transform: 'translateX(0)' },
        ], { duration: 420 })
        emoteSound(emote.flight === 'float')
        node.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 300, fill: 'forwards' })
      }).catch(() => undefined)
    }
    if (emote.kind === 'reaction' || !to) emoteSound(true)
    const finish = () => window.setTimeout(() => done(show.key), 400)
    animation.onfinish = finish
    return () => animation.cancel()
  }, [show, done])
  const emote = EMOTE[show.emote]
  if (!emote) return null
  return <span ref={element} className="emote-flight" data-kind={emote.kind} aria-hidden="true">
    <span className="emote-emoji">{emote.emoji}</span>
    {(emote.kind === 'reaction' || !show.to) && <span className="emote-label">{emote.label}</span>}
  </span>
}

export default function EmoteLayer({ shows, done }: { shows: Show[]; done: (key: number) => void }) {
  return <div className="emote-layer">{shows.map(show => <Play key={show.key} show={show} done={done} />)}</div>
}
