import { useEffect, useState } from 'react'
import { setSound, soundEnabled, unlockSound } from './sound'

export default function SoundToggle() {
  const [enabled, setEnabled] = useState(soundEnabled)
  useEffect(() => {
    window.addEventListener('pointerup', unlockSound)
    window.addEventListener('keydown', unlockSound)
    return () => {
      window.removeEventListener('pointerup', unlockSound)
      window.removeEventListener('keydown', unlockSound)
    }
  }, [])
  return <button className="quiet" type="button" aria-label="Sound effects" aria-pressed={enabled}
    title={enabled ? 'Mute sound effects' : 'Enable sound effects'}
    onClick={() => { setSound(!enabled); setEnabled(!enabled) }}>
    <span aria-hidden="true">{enabled ? '🔊' : '🔇'}</span>
  </button>
}
