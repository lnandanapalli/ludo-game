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
  return <label className="preference">Sound effects
    <input type="checkbox" checked={enabled} onChange={e => {
      setSound(e.target.checked)
      setEnabled(e.target.checked)
    }}/>
  </label>
}
