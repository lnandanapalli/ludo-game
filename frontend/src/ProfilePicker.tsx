import type { Profile } from './api'
import { portraits } from './profiles'

export default function ProfilePicker({ seat, profile, change, autoMove, onAutoMove }: {
  autoMove: boolean; onAutoMove: (enabled: boolean) => void
  seat: string; profile: Profile; change: (profile: Profile) => void
}) {
  return <fieldset className="profile-picker" data-seat={seat}><legend>{seat} player</legend>
    <input aria-label={seat + ' player name'} maxLength={24} placeholder="Player name" value={profile.name}
      onChange={e => change({...profile, name: e.target.value})}/>
    <div className="portraits">{Object.entries(portraits).map(([id, face]) =>
      <button key={id} type="button" aria-label={seat + ' ' + id} aria-pressed={profile.avatar === id}
        onClick={() => change({...profile, avatar: id})}>{face}</button>)}</div>
    <label className="preference">Move automatically when only one pawn can move
      <input type="checkbox" checked={autoMove} onChange={e => onAutoMove(e.target.checked)}/>
    </label>
  </fieldset>
}
